# -*- coding: utf-8 -*-
# @module get_event_invoice_context.py
# @changed 2024.03.22, 19:21

import logging
import traceback
from datetime import date

from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.http import HttpRequest

from ..core.constants.date_time_formats import dateFormat
from ..core.helpers.errors import errorToString

from ..models import (
    REGISTRATION_ACTIVE_QUERY,
    Event,
    Registration,
    RegistrationOption,
    User,
    Invoice,
)
from .helpers import (
    calculate_total_registration_price,
    get_full_user_name,
)

LOG = logging.getLogger(__name__)

# Default dds parameters

# TODO: To store them in constants or in the settings or configuration?

dds_name = "Départ de Sentier"
dds_address = """
Dorfsteig 8
5223 Riniken
Switzerland
VAT CHE-329.638.515
"""
default_payment_details = """
Account Holder: Départ de Sentier, Dorfsteig 8, 5223 Riniken AG, Switzerland
Bank: Wise, Avenue Louise 54, Room S52, 1050 Brussels, Belgium
IBAN: BE31 9673 6729 9455
SWIFT-BIC: TRWIBEB1XXX
"""

table_header = (
    # Header...
    "Quantity",
    "Event",
    "Option",
    "Costs (EUR)",
)


def get_event_text(event: Event) -> str:
    text = "**{}**".format(event.title)
    if event.description:
        text += "\n" + event.description
    return text


def create_services_table(user: User, event: Event, registration: Registration):
    table = (table_header,)
    # options = registration.options.all()
    option = registration.option
    options = [option]
    event_text = get_event_text(event)
    #  count = 1
    total = 0

    def add_option_row(opt: RegistrationOption):
        nonlocal total
        row_data = (
            1,
            event_text,
            opt.item,
            opt.price if opt.price else "",
        )
        if opt.price:
            total += opt.price
        #  count += 1
        return row_data

    rows_basic = tuple(map(add_option_row, options))
    rows_addon = []  # tuple(map(add_option_row, options.filter(add_on=True)))
    total_row = (
        "",
        "__Total__",
        "",
        "__{}__".format(total),
    )
    table = (*table, *rows_basic, *rows_addon, total_row)
    # TODO: addons, total
    return table


def check_is_event_invoice_ready(request: HttpRequest, event_code: str):
    """
    Check if there already is an invoice for this event/registration.
    Create it if it doesn't already exist.
    """
    user: User = request.user
    # Check for non-anonymous user...
    if not user or not user.id:
        raise Exception("Required registered user")
    context = {
        "event_code": event_code,
        "user": user,
        "site": get_current_site(request),
    }
    event: Event | None = None
    registration: Registration | None = None
    invoice: Invoice | None = None
    # Try to get event object by code...
    try:
        event = Event.objects.get(code=event_code)
        registration = event.registrations.get(REGISTRATION_ACTIVE_QUERY, user=user)
        if not registration:
            raise Exception("Not found active registration")
        invoice = registration.invoice
        if not invoice:
            invoice = Invoice()
        #  # UNUSED: Address has integrated into the base user model
        #  profile, created = .get_or_create(user=user)
        table_data = create_services_table(user, event, registration)
        payment_deadline_days = event.payment_deadline_days
        # TInvoicePdfParams data...
        optional_text = ""  # registration.extra_invoice_text
        client_name = get_full_user_name(user)
        client_address = user.address  # profile.address
        today = date.today()
        # NOTE: Probably the year in the invoice id should rely on the registration date, not on the invoice creatiion one?
        year_str = today.strftime("%y")
        invoice_date = today.strftime(dateFormat)
        invoice_no = "TODO"  # "#{}{:0>4}".format(year_str, registration.invoice_no)
        payment_terms = "Within **{} business days** of invoice issuance".format(payment_deadline_days)
        payment_details = event.payment_details if event.payment_details else default_payment_details
        # TInvoicePdfParams data...
        context["event"] = event
        context["registration"] = registration
        context["optional_text"] = optional_text
        context["client_name"] = client_name
        context["client_address"] = client_address
        context["dds_name"] = dds_name
        context["dds_address"] = dds_address
        context["invoice_no"] = invoice_no
        context["invoice_date"] = invoice_date
        context["payment_terms"] = payment_terms
        context["payment_details"] = payment_details
        context["table_data"] = table_data
    except Exception as err:
        sError = errorToString(err, show_stacktrace=False)
        error_text = 'Not found event code "{}": {}'.format(event_code, sError)
        messages.error(request, error_text)
        sTraceback = str(traceback.format_exc())
        debug_data = {
            "event_code": event_code,
            "err": err,
            "traceback": sTraceback,
        }
        LOG.error("%s (redirecting to profile): %s", error_text, debug_data)
        raise Exception(error_text)

    return get_event_invoice_context(request, event_code)


def get_event_invoice_context(request: HttpRequest, event_code: str):
    user: User = request.user
    scheme = "https" if request.is_secure() else "http"
    context = {
        "event_code": event_code,
        "user": user,
        "site": get_current_site(request),
        "scheme": scheme,
    }
    event: Event | None = None
    registration: Registration | None = None
    # Try to get event object by code...
    try:
        event = Event.objects.get(code=event_code)
        registration = event.registrations.get(REGISTRATION_ACTIVE_QUERY, user=user)
        # registration = event.registrations.get(user=user, active=True)
        if not registration:
            raise Exception("Not found active registration")
        #  # UNUSED: Address has integrated into the base user model
        #  profile, created = .get_or_create(user=user)
        table_data = create_services_table(user, event, registration)
        payment_deadline_days = event.payment_deadline_days
        # TInvoicePdfParams data...
        optional_text = ""  # registration.extra_invoice_text
        client_name = get_full_user_name(user)
        client_address = user.address  # profile.address
        today = date.today()
        # NOTE: Probably the year in the invoice id should rely on the registration date, not on the invoice creatiion one?
        year_str = today.strftime("%y")
        invoice_date = today.strftime(dateFormat)
        invoice_no = "TODO"  # "#{}{:0>4}".format(year_str, registration.invoice_no)
        payment_terms = "Within **{} business days** of invoice issuance".format(payment_deadline_days)
        payment_details = event.payment_details if event.payment_details else default_payment_details
        # TInvoicePdfParams data...
        context["event"] = event
        context["registration"] = registration
        context["optional_text"] = optional_text
        context["client_name"] = client_name
        context["client_address"] = client_address
        context["dds_name"] = dds_name
        context["dds_address"] = dds_address
        context["invoice_no"] = invoice_no
        context["invoice_date"] = invoice_date
        context["payment_terms"] = payment_terms
        context["payment_details"] = payment_details
        context["table_data"] = table_data
    except Exception as err:
        sError = errorToString(err, show_stacktrace=False)
        error_text = 'Not found event code "{}": {}'.format(event_code, sError)
        messages.error(request, error_text)
        sTraceback = str(traceback.format_exc())
        debug_data = {
            "event_code": event_code,
            "err": err,
            "traceback": sTraceback,
        }
        LOG.error("%s (redirecting to profile): %s", error_text, debug_data)
        raise Exception(error_text)

    context["event"] = event
    context["registration"] = registration
    context["total_price"] = calculate_total_registration_price(registration)
    return context
