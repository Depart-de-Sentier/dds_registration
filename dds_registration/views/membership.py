# @module dds_registration/views/membership.py
# @changed 2024.03.27, 16:46

import logging
import traceback
import json

from django.contrib.sites.shortcuts import get_current_site
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect, HttpResponseRedirect
from django.shortcuts import redirect, render

from ..core.helpers.errors import errorToString

from ..core.constants.stripe_payments import (
    academic_membership_stripe_payment_link,
    regular_membership_stripe_payment_link,
)

#  from ..core.helpers.create_invoice_pdf import create_invoice_pdf
#  from ..core.helpers.errors import errorToString

#  from .get_event_invoice_context import get_event_invoice_context

from ..models import Membership


LOG = logging.getLogger(__name__)


# TODO: Revoke membership?


class check_for_available_membership:
    """
    Check if it's possible to apply for a membership
    """

    response: None | HttpResponsePermanentRedirect | HttpResponseRedirect = None
    success: bool = False

    def __init__(self, request: HttpRequest):
        self.success = True  # Assume success by default
        user = request.user
        # Check for the existing membership...
        if user.is_authenticated:
            memberships = Membership.objects.filter(user=user)
            # Are there memberships for this user?
            if memberships and len(memberships):
                messages.success(request, "You're already a member (or waiting for your membership activation)")
                # TODO: Display the membership data on the profile page?
                self.response = redirect("profile")
                self.success = False

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        pass


def check_if_it_possible_to_become_a_member(request: HttpRequest):
    user = request.user
    # Check for the existing membership...
    if user.is_authenticated:
        memberships = Membership.objects.filter(user=user)
        # Has member user(s)?
        if memberships and len(memberships):
            messages.success(request, "You're already a member (or waiting for your membership activation)")
            # TODO: Display the membership data on the profile page?
            return redirect("profile")
    return None


def membership_start(request: HttpRequest):
    with check_for_available_membership(request) as checked:
        if checked.response:
            return checked.response
    # Display a membership options form...
    context = {
        "MEMBERSHIP_TYPES": Membership.MEMBERSHIP_TYPES,
        "membership_type": Membership.DEFAULT_MEMBERSHIP_TYPE,
    }
    debug_data = context
    LOG.debug("membership_start: %s", debug_data)
    return render(request, "dds_registration/membership_start.html.django", context)


@login_required
def membership_proceed(request: HttpRequest):
    try:
        user = request.user
        if not user.is_authenticated:
            messages.error(request, "Authorization is required in order to create a membership")
            return redirect("index")
        with check_for_available_membership(request) as checked:
            if checked.response:
                return checked.response
        # Proceed...
        membership_type = request.GET.get("membership_type")
        if not membership_type:
            messages.error(request, "You have to choose membership type")
            return redirect("membership_start")
        is_invoice = Membership.is_membership_type_invoice(membership_type)
        is_academic = Membership.is_membership_type_academic(membership_type)
        debug_data = {
            "is_invoice": is_invoice,
            "is_academic": is_academic,
            "membership_type": membership_type,
            "request": request,
        }
        LOG.debug("membership_proceed: %s", debug_data)
        membership = Membership()
        membership.membership_type = membership_type
        membership.user = user
        membership.save()
        # Invoice option: show invoice result...
        if is_invoice:
            return redirect("membership_proceed_invoice")
        # Go to stripe site...
        stripe_link = academic_membership_stripe_payment_link if is_academic else regular_membership_stripe_payment_link
        return redirect(stripe_link)
    except Exception as err:
        sError = errorToString(err, show_stacktrace=False)
        sTraceback = str(traceback.format_exc())
        error_text = "Can not proceed membership: {}".format(sError)
        messages.error(request, error_text)
        debug_data = {
            "err": err,
            "traceback": sTraceback,
            "sError": sError,
        }
        LOG.error("%s (redirecting to profile): %s", error_text, debug_data)
        # Redirect to profile page with error messages (see above)
        return redirect("profile")


@login_required
def membership_proceed_success(request: HttpRequest):
    context = {
        "action": "membership_proceed_success",
    }
    return render(request, "dds_registration/membership_test.html.django", context)


def membership_proceed_test(request: HttpRequest, payment_id: str):
    try:
        scheme = "https" if request.is_secure() else "http"
        site = get_current_site(request)
        debug_data = {
            "scheme": scheme,
            "payment_id": payment_id,
            #  "method": method,
            #  "request": request,
        }
        LOG.debug("membership_proceed_test: %s", debug_data)
        context = {
            "action": "membership_proceed_test",
        }
        return render(request, "dds_registration/membership_test.html.django", context)
    except Exception as err:
        sError = errorToString(err, show_stacktrace=False)
        sTraceback = str(traceback.format_exc())
        error_text = "Error on membership_test: {}".format(sError)
        messages.error(request, error_text)
        debug_data = {
            "err": err,
            "traceback": sTraceback,
            "sError": sError,
        }
        LOG.error("%s (re-raising): %s", error_text, debug_data)
        # Redirect to profile page with error messages (see above)
        #  return redirect("profile")
        raise err


#  @login_required
#  def membership_proceed_invoice(request: HttpRequest):
#      # TODO: Generate invoice pdf
#      template = "dds_registration/membership_invoice.html.django"
#      context = get_event_invoice_context(request, event_code)
#      show_debug = False
#      if show_debug:
#          return render(request, template, context)
#      pdf = create_invoice_pdf(context)
#      return HttpResponse(bytes(pdf.output()), content_type="application/pdf")


@csrf_exempt
def membership_stripe_webhook(request: HttpRequest):
    try:
        method = request.method
        if method != "POST":
            raise Exception("Expecting post data request")
        json_payload = request.body.decode("utf-8")
        payload = json.loads(json_payload)
        data = payload["data"] if "data" in payload else {}
        object = data["object"] if "object" in data else {}
        payload_type = payload.get("type")  # Expecting `payment_intent.succeeded`
        payload_request = payload.get("request")
        status = object.get("status")  # Expecting 'succeeded'
        #  Parsed data example:
        #  'id': 'evt_3OybccL41uPceS6J0bUl44n0'
        #  'object': 'event'
        #  'api_version': '2022-11-15'
        #  'created': 1711465746
        #  'data': {'object': {'id': 'pi_3OybccL41uPceS6J07wyCykn', 'object': 'payment_intent', 'amount': 2000, 'amount_capturable': 0, 'amount_details': {...}, 'amount_received': 0, 'application': None, 'application_fee_amount': None, 'automatic_payment_methods': None, 'canceled_at': None, 'cancellation_reason': None, 'capture_method': 'automatic', 'client_secret': 'pi_3OybccL41uPceS6J07wyCykn_secret_QR4X27IfkXe58qhNUTn6W9LaY', 'confirmation_method': 'automatic', 'created': 1711465746, 'currency': 'usd', 'customer': None, 'description': '(created by Stripe CLI)', 'invoice': None, ...}}
        #  'livemode': False
        #  'pending_webhooks': 2
        #  'request': {'id': 'req_vurnMXFvwMjR9n', 'idempotency_key': 'af178ca4-a2b6-43c3-af8a-b227a60ffc20'}
        #  'type': 'payment_intent.created'
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
        debug_data = {
            "payload_type": payload_type,
            "payload_request": payload_request,
            "status": status,
            #  "object": object,
            #  "data": data,
            #  "parsed": parsed,
            "payload": payload,
            "sig_header": sig_header,
            #  "method": method,
            #  "request": request,
        }
        LOG.debug("membership_stripe_webhook: %s", debug_data)
        context = {
            "action": "membership_stripe_webhook",
        }
        return render(request, "dds_registration/membership_test.html.django", context)
    except Exception as err:
        sError = errorToString(err, show_stacktrace=False)
        sTraceback = str(traceback.format_exc())
        error_text = "Error processing stripe webhook: {}".format(sError)
        messages.error(request, error_text)
        debug_data = {
            "err": err,
            "traceback": sTraceback,
            "sError": sError,
        }
        LOG.error("%s (re-raising): %s", error_text, debug_data)
        # Redirect to profile page with error messages (see above)
        #  return redirect("profile")
        raise err
