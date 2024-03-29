# @module dds_registration/views/billing.py
# @changed 2024.03.28, 18:41

import logging
import traceback

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from ..core.helpers.create_invoice_pdf import create_invoice_pdf
from ..core.helpers.errors import errorToString

from ..forms import BillingEventForm
from ..models import Invoice

from .get_invoice_context import (
    get_basic_event_registration_context,
    get_event_invoice_context,
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
    try:
        user = request.user
        if not user.is_authenticated:
            return redirect("index")
        # TODO: Check if invoice has been already created?
        context = get_basic_event_registration_context(request, event_code)
        # TODO: Catch registration doesn't exist
        # event = context["event"]
        registration = context["registration"]
        invoice = context["invoice"]
        is_new = False
        if not invoice:
            is_new = True
            # Create default invoice and initialize default values...
            invoice = Invoice()
            invoice.name = user.get_full_name()
            invoice.address = user.address
        context_redirect = context.get("redirect")
        if context_redirect:
            return context_redirect
        if request.method == "POST":
            # Create a form instance and populate it with data from the request:
            form = BillingEventForm(request.POST, instance=invoice)
            # Check whether it's valid:
            if form.is_valid():
                cleaned_data = form.cleaned_data
                invoice = form.save()
                #  invoice.registration.set(registration)
                debug_data = {
                    "cleaned_data": cleaned_data,
                    "invoice": invoice,
                }
                LOG.debug("Get form data: %s", debug_data)
                new_verb = "created" if is_new else "updated"
                messages.success(request, "Invoice has been successfully " + new_verb)
                # TODO: What if changing an existing invoice and the `payment_method` parameter has changed?
                invoice.save()
                # Update registration...
                registration.invoice = invoice  # Link the invoice
                registration.status = "PAYMENT_PENDING"  # Change the status -- now we're expecting the payment
                registration.save()
                # TODO: Redirect to invoice downloading or to payment page?
                redirect_to = (
                    "billing_event_success_invoice"
                    if invoice.payment_method == "INVOICE"
                    else "billing_event_success_payment"
                )
                return redirect(redirect_to, event_code=event_code)
        else:
            form = BillingEventForm(instance=invoice)
        context["form"] = form
        template = "dds_registration/billing/billing_event_form.html.django"
        return render(request, template, context)
    except Exception as err:
        sError = errorToString(err, show_stacktrace=False)
        error_text = 'Cannot process Billing for the event "{}": {}'.format(event_code, sError)
        messages.error(request, error_text)
        sTraceback = str(traceback.format_exc())
        debug_data = {
            "event_code": event_code,
            "err": err,
            "traceback": sTraceback,
        }
        LOG.error("%s (redirecting to profile): %s", error_text, debug_data)
        raise Exception(error_text)


@login_required
def billing_event_success_invoice(request: HttpRequest, event_code: str):
    """
    Show page with information about successfull invoice creation and a link to
    download it.
    """
    context = get_basic_event_registration_context(request, event_code)
    template = "dds_registration/billing/billing_event_success_invoice.html.django"
    return render(request, template, context)


@login_required
def billing_event_invoice_download(request: HttpRequest, event_code: str):
    """
    Show page with information about successfull invoice creation and a link to
    download it.
    """
    context = get_event_invoice_context(request, event_code)
    show_debug = False
    if show_debug:
        # DEBUG: Show test page with prepared invoice data
        template = "dds_registration/billing/billing_event_invoice_download_debug.html.django"
        return render(request, template, context)
    pdf = create_invoice_pdf(context)
    return HttpResponse(bytes(pdf.output()), content_type="application/pdf")


@login_required
def billing_event_success_payment(request: HttpRequest, event_code: str):
    """
    Show page with information about successfull payment creation and a link to
    proceed it.
    """
    context = {
        "page": "billing_event_success_payment",
    }
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


__all__ = []
