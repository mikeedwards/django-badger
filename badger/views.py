import jingo
import logging
import random
import datetime

from django.conf import settings

from django.http import (HttpResponseRedirect, HttpResponse,
        HttpResponseForbidden, HttpResponseNotFound)

from django.utils import simplejson

from django.shortcuts import get_object_or_404, render_to_response
from django.template import RequestContext
from django.template.defaultfilters import slugify

from quota.models import PrizeCode

try:
    from commons.urlresolvers import reverse
except ImportError, e:
    from django.core.urlresolvers import reverse

try:
    from tower import ugettext_lazy as _
except ImportError, e:
    from django.utils.translation import ugettext_lazy as _

from django.views.generic.base import View
from django.views.generic.list_detail import object_list
from django.views.decorators.http import (require_GET, require_POST,
                                          require_http_methods)

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User

from .models import (Progress,
        BadgeAwardNotAllowedException)

# TODO: Is there an extensible way to do this, where "add-ons" introduce proxy
# model objects?
try:
    from badger_multiplayer.models import Badge, Award
except ImportError:
    from badger.models import Badge, Award

from .forms import (BadgeAwardForm)

BADGE_PAGE_SIZE = 21
MAX_RECENT = 10


def home(request):
    """Badger home page"""
    return render_to_response('badger/home.html', dict(
        badge_list=Badge.objects.order_by('-modified').all()[:MAX_RECENT],
        award_list=Award.objects.order_by('-modified').all()[:MAX_RECENT],
    ), context_instance=RequestContext(request))


def badges_list(request):
    """Badges list page"""
    query_string = request.GET.get('q', None)
    if query_string is not None:
        sort_order = request.GET.get('sort', 'created')
        queryset = Badge.objects.search(query_string, sort_order)
    else: 
        queryset = Badge.objects.order_by('-modified').all()
    return object_list(request, queryset,
        paginate_by=BADGE_PAGE_SIZE, allow_empty=True,
        extra_context=dict(
            query_string=query_string
        ),
        template_object_name='badge',
        template_name='badger/badges_list.html')


@require_GET
def detail(request, slug, format="html"):
    """Badge detail view"""
    badge = get_object_or_404(Badge, slug=slug)
    awards = (Award.objects.filter(badge=badge)
                           .order_by('-created'))[:MAX_RECENT]

    if format == 'json':
        data = badge.as_obi_serialization(request)
        resp = HttpResponse(simplejson.dumps(data))
        resp['Content-Type'] = 'application/json'
        return resp
    else:
        allow_award = badge.allows_award_to(request.user)
        return render_to_response('badger/badge_detail.html', dict(
            badge=badge, award_list=awards,allow_award=allow_award,
        ), context_instance=RequestContext(request))


@require_http_methods(['GET', 'POST'])
@login_required
def award_badge(request, slug):
    """Issue an award for a badge"""
    badge = get_object_or_404(Badge, slug=slug)
    if not badge.allows_award_to(request.user):
        return HttpResponseForbidden()

    if request.method != "POST":
        form = BadgeAwardForm()
    else:
        form = BadgeAwardForm(request.POST, request.FILES)
        if form.is_valid():
            award = badge.award_to(form.cleaned_data['user'], request.user)
            return HttpResponseRedirect(reverse(
                    'badger.views.award_detail', 
                    args=(badge.slug, award.id, )))

    return render_to_response('badger/badge_award.html', dict(
        form=form, badge=badge,
    ), context_instance=RequestContext(request))


@require_GET
def awards_list(request, slug=None):
    queryset = Award.objects
    if not slug:
        badge = None
    else:
        badge = get_object_or_404(Badge, slug=slug)
        queryset = queryset.filter(badge=badge)
    queryset = queryset.order_by('-modified').all()

    return object_list(request, queryset,
        paginate_by=BADGE_PAGE_SIZE, allow_empty=True,
        extra_context=dict(
            badge=badge
        ),
        template_object_name='award',
        template_name='badger/awards_list.html')


@require_GET
def award_detail(request, slug, id, format="html"):
    """Award detail view"""
    badge = get_object_or_404(Badge, slug=slug)
    award = get_object_or_404(Award, badge=badge, pk=id)

    if format == 'json':
        data = simplejson.dumps(award.as_obi_assertion(request))
        resp = HttpResponse(data)
        resp['Content-Type'] = 'application/json'
        return resp
    else:
        return render_to_response('badger/award_detail.html', dict(
            badge=badge, award=award,
        ), context_instance=RequestContext(request))


@require_GET
def awards_by_user(request, username):
    """Badge awards by user"""
    user = get_object_or_404(User, username=username)
    awards = Award.objects.filter(user=user)
    for award in awards:
        key = "%s_%s_badge_%s" % (user.username, PrizeCode.BADGE_AWARD, award.badge.slug) 
        prize_code = PrizeCode(user=user, award_type=PrizeCode.BADGE_AWARD, date=datetime.date.today(), amount=award.badge.points)
        prize_code.set_key(key)
        try:
            prize_code = PrizeCode.objects.get(key_md5=prize_code.key_md5)
        except PrizeCode.DoesNotExist:
            prize_code.save()
        award.__setattr__('prize_code',prize_code)

    return render_to_response('badger/awards_by_user.html', dict(
        user=user, award_list=awards,
    ), context_instance=RequestContext(request))


@require_GET
def awards_by_badge(request, slug):
    """Badge awards by badge"""
    badge = get_object_or_404(Badge, slug=slug)
    awards = Award.objects.filter(badge=badge)
    return render_to_response('badger/awards_by_badge.html', dict(
        badge=badge, awards=awards,
    ), context_instance=RequestContext(request))
