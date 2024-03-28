# @module dds_registration/views/event_registration.py
# @changed 2024.03.19, 01:40

import logging
import traceback

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from ..core.helpers.create_invoice_pdf import create_invoice_pdf
from ..core.helpers.errors import errorToString

from .event_registration_cancel import (
    event_registration_cancel_confirm_form,
    event_registration_cancel_process_action,
)
from .get_invoice_context import get_event_invoice_context, check_is_event_invoice_ready
from .helpers import (
    event_registration_form,
    get_event_registration_context,
    show_registration_form_success,
)

LOG = logging.getLogger(__name__)


@login_required
def billing_event(request: HttpRequest, event_code: str):
    """
    Show the form to select payment options:
    - RegistrationOption (from available ones for this event)
    - `payment_method`: Payment method (either Credit Card or Invoice)
    - `extra_invoice_text`: Extra information they might want to add to the
      Invoice (help text is "Any additional text for the invoice, such as a
      reference or purchase order number").

    Form should display the name and address that we have for that user account.

    Users must be logged in, and registered for the event - otherwise they get
    redirected to the homepage.

    If they are registered, then they have chosen a RegistrationOption, so we
    can use that to look up the price and currency.

    """
    user = request.user
    if not user.is_authenticated:
        return redirect('index')
    # TODO: Check if invoice has been already created?
    context = check_is_event_invoice_ready(request, event_code)
    context_redirect = context.get("redirect")
    if context_redirect:
        return redirect(context_redirect)
    template = "dds_registration/billing/billing_test.html.django"
    return render(request, template, context)


@login_required
def billing_membership(request: HttpRequest):
    """
    The first thing users need to do is select if this is an academic,
    business, or normal membership (see `Membership.membership_type`).
    """
    context = {}
    template = "dds_registration/billing/billing_test.html.django"
    return render(request, template, context)


__all__ = [
]
