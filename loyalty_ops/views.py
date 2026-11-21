"""Authenticated staff pages: no customer-facing login and no automatic payouts."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from core.models import Branch
from pos.models import Sale
from pos.permissions import visible_sales
from .forms import MemberForm, ReceiptForm, RewardForm
from .models import LoyaltyMember, LoyaltyReward, LoyaltyRedemption
from .permissions import permitted_branch
from .services import balance_for, enroll_member, link_paid_sale, reserve_reward, review_redemption


def scoped_members(branch):
    query = LoyaltyMember.objects.select_related('branch')
    return query if branch is None else query.filter(branch=branch)


def scoped_rewards(branch):
    query = LoyaltyReward.objects.select_related('branch')
    return query if branch is None else query.filter(branch=branch)


def add_errors(request, error):
    for e in error.messages if isinstance(error, ValidationError) else [str(error)]:
        messages.error(request, e)


@login_required
@require_GET
def home(request):
    branch = permitted_branch(request)
    q = (request.GET.get('q') or '').strip()[:100]
    members = scoped_members(branch)
    if q:
        members = members.filter(Q(member_code__icontains=q) | Q(full_name__icontains=q) | Q(phone__icontains=q))
    page = Paginator(members, 25).get_page(request.GET.get('page'))
    return render(request, 'loyalty_ops/home.html', {'page': page, 'q': q, 'branch': branch})


@login_required
@require_http_methods(['GET', 'POST'])
def enroll(request):
    branch = permitted_branch(request)
    form = MemberForm(request.POST or None, initial={'branch': branch} if branch else None)
    if branch is not None:
        form.fields['branch'].queryset = Branch.objects.filter(pk=branch.pk)
    if request.method == 'POST' and form.is_valid():
        selected = form.cleaned_data['branch']
        if branch is not None and selected.pk != branch.pk:
            raise PermissionDenied('Cannot enroll customers in another branch.')
        try:
            member = enroll_member(branch=selected, full_name=form.cleaned_data['full_name'],
                                   phone=form.cleaned_data['phone'], consent=form.cleaned_data['consent'], actor=request.user)
        except ValidationError as exc:
            add_errors(request, exc)
        else:
            messages.success(request, 'Member enrolled with customer consent. Give the customer their member code.')
            return redirect('loyalty_ops:member', pk=member.pk)
    return render(request, 'loyalty_ops/enroll.html', {'form': form})


@login_required
@require_GET
def member_detail(request, pk):
    branch = permitted_branch(request)
    member = get_object_or_404(scoped_members(branch), pk=pk)
    purchases = member.loyalty_purchases.select_related('sale').order_by('-linked_at')[:40]
    redemptions = member.loyalty_redemptions.select_related('reward', 'requested_by').order_by('-created_at')[:40]
    rewards = scoped_rewards(branch).filter(branch_id=member.branch_id, active=True, points_cost__gt=0)
    return render(request, 'loyalty_ops/member.html', {
        'member': member, 'summary': balance_for(member), 'purchases': purchases,
        'redemptions': redemptions, 'rewards': rewards, 'receipt_form': ReceiptForm(),
    })


@login_required
@require_POST
def link_receipt(request, pk):
    branch = permitted_branch(request)
    member = get_object_or_404(scoped_members(branch), pk=pk)
    form = ReceiptForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Enter an existing POS receipt number.')
        return redirect('loyalty_ops:member', pk=pk)
    number = form.cleaned_data['receipt_number'].strip().upper()
    sale = get_object_or_404(visible_sales(request).filter(branch=member.branch), receipt_number=number)
    try:
        link_paid_sale(member=member, sale=sale, actor=request.user)
    except (ValidationError, ValueError) as exc:
        add_errors(request, exc)
    else:
        messages.success(request, 'Paid sale linked. Points were calculated on the final receipt total.')
    return redirect('loyalty_ops:member', pk=pk)


@login_required
@require_POST
def redeem(request, pk):
    branch = permitted_branch(request)
    member = get_object_or_404(scoped_members(branch), pk=pk)
    raw = request.POST.get('reward_id', '')
    if not raw.isascii() or not raw.isdigit():
        raise Http404('Invalid reward.')
    reward = get_object_or_404(scoped_rewards(branch), pk=int(raw), branch=member.branch)
    try:
        reserve_reward(member=member, reward=reward, actor=request.user)
    except ValidationError as exc:
        add_errors(request, exc)
    else:
        messages.success(request, 'Reward reserved. Points deducted. Manager must record fulfillment or cancellation.')
    return redirect('loyalty_ops:member', pk=pk)


@login_required
@require_http_methods(['GET', 'POST'])
def rewards(request):
    branch = permitted_branch(request, manager=True)
    form = RewardForm(request.POST or None, initial={'branch': branch} if branch else None)
    if branch is not None:
        form.fields['branch'].queryset = Branch.objects.filter(pk=branch.pk)
    if request.method == 'POST' and form.is_valid():
        reward = form.save(commit=False)
        if branch is not None and reward.branch_id != branch.pk:
            raise PermissionDenied('Cannot create another branch reward.')
        if reward.points_cost < 1:
            form.add_error('points_cost', 'Use at least one point.')
        else:
            reward.created_by = request.user
            reward.full_clean()
            reward.save()
            messages.success(request, 'Reward registered. Any stock or value delivered must be recorded in its normal workflow.')
            return redirect('loyalty_ops:rewards')
    available = scoped_rewards(branch).order_by('title')[:100]
    pending = LoyaltyRedemption.objects.select_related('member', 'reward')\
        .filter(state=LoyaltyRedemption.State.RESERVED)
    if branch is not None:
        pending = pending.filter(member__branch=branch)
    return render(request, 'loyalty_ops/rewards.html', {
        'form': form, 'rewards': available, 'pending': pending[:100],
    })


@login_required
@require_POST
def review(request, pk):
    branch = permitted_branch(request, manager=True)
    pending = LoyaltyRedemption.objects.select_related('member', 'reward')
    if branch is not None:
        pending = pending.filter(member__branch=branch)
    redemption = get_object_or_404(pending, pk=pk)
    action = request.POST.get('action')
    target = {'fulfill': LoyaltyRedemption.State.FULFILLED,
              'cancel': LoyaltyRedemption.State.CANCELLED}.get(action)
    try:
        review_redemption(redemption=redemption, actor=request.user,
                          state=target, reference=request.POST.get('reference'))
    except ValidationError as exc:
        add_errors(request, exc)
    else:
        messages.success(request, 'Reward status recorded. No automated payment or stock adjustment performed.')
    return redirect('loyalty_ops:rewards')


@login_required
@require_POST
def toggle_member(request, pk):
    branch = permitted_branch(request, manager=True)
    with transaction.atomic():
        member = get_object_or_404(scoped_members(branch).select_for_update(), pk=pk)
        member.active = not member.active
        member.save(update_fields=['active'])
    messages.success(request, 'Member status changed.')
    return redirect('loyalty_ops:member', pk=pk)
