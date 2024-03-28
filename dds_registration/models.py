# @module models.py
# @changed 2024.03.28, 19:28

import random
import string
from datetime import date
from functools import partial

from django.conf import settings
from django.contrib.auth.models import AbstractUser, Group
from django.contrib.sites.models import Site  # To access site properties
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Model, Q
from django.urls import reverse

# from queryable_properties.properties import queryable_property

from .core.constants.date_time_formats import (
    #  dateTimeFormat,
    #  onlyDateFormat,
    dateFormat,
)
from .core.helpers.dates import this_year


alphabet = string.ascii_lowercase + string.digits
random_code_length = 8


def random_code(length=random_code_length):
    return "".join(random.choices(alphabet, k=length))


class User(AbstractUser):

    # NOTE: It seems to be imposible to completely remove the `username` because it's used in django_registration
    # username = None

    email = models.EmailField(unique=True)
    address = models.TextField(blank=True, default="")

    # NOTE: Using the email field for the username is incompatible with `django_registration`:
    # @see https://django-registration.readthedocs.io/en/3.4/custom-user.html#compatibility-of-the-built-in-workflows-with-custom-user-models
    # The username and email fields must be distinct. If you wish to use the
    # email address as the username, you will need to write your own completely
    # custom registration form.

    # Username isn't used by itself, but it's still used in the django_registration internals. Both these fields are synced.

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    # These variables are used to determine if email or username have changed on save
    _original_email = None
    _original_username = None

    class Meta(AbstractUser.Meta):
        #  # TODO: Add correct check if email and username are the same?
        #  constraints = [
        #      models.CheckConstraint(
        #          check=Q(email=models.F('username')),
        #          name='username_is_email',
        #      )
        #  ]
        pass

    def sync_email_and_username(self):
        # Check if email or username had changed?
        email_changed = self.email != self._original_email
        username_changed = self.username != self._original_username
        # Auto sync username and email
        if email_changed:
            self.username = self.email
        elif username_changed:
            self.email = self.username
        if email_changed or username_changed:
            self._original_email = self.email
            self._original_username = self.username
            # TODO: To do smth else if email has changed?

    def get_full_name_with_email(self):
        name = self.get_full_name()
        email = self.email
        if not name and email:
            name = email
        items = [
            name,
            "<{}>".format(email) if email and email != name else "",
        ]
        info = "  ".join(filter(None, map(str, items)))
        return info

    @property
    def full_name_with_email(self):
        return self.get_full_name_with_email()

    def clean(self):
        # NOTE: This method is called before `save`: it's useless to compare email and here
        #  from django.core.exceptions import ValidationError
        #  if self.email != self.username:
        #      raise ValidationError('Email and username should be equal')
        self.sync_email_and_username()
        return super(User, self).clean()

    def save(self, *args, **kwargs):
        self.sync_email_and_username()
        return super(User, self).save(*args, **kwargs)

    def __init__(self, *args, **kwargs):
        super(User, self).__init__(*args, **kwargs)
        self._original_email = self.email
        self._original_username = self.username


class Membership(Model):
    MEMBERSHIP_TYPES = [
        ("NORMAL", "Normal"),
        ("BOARD", "Board member"),
        ("HONORARY", "Honorary"),
        ("BUSINESS", "Business"),
        ("ACADEMIC", "Academic"),  # NOTE: For 'academic' (discounted) payment type
    ]
    DEFAULT_MEMBERSHIP_TYPE = "NORMAL"

    # NOTE: Old membership type definition (TODO: Remove after refactor finishes)
    #  # Membership type:
    #  MEMBERSHIP_TYPES = (
    #      ("NORMAL_CREDIT_CARD", "Normal membership - Pay by credit card"),
    #      ("NORMAL_INVOICE", "Normal membership - Pay by invoice"),
    #      ("ACADEMIC_CREDIT_CARD", "Academic membership - Pay by credit card"),
    #      ("ACADEMIC_INVOICE", "Academic membership - Pay by invoice"),
    #  )
    #  DEFAULT_MEMBERSHIP_TYPE = "NORMAL_CREDIT_CARD"
    #  membership_type = models.TextField(choices=MEMBERSHIP_TYPES, default=DEFAULT_MEMBERSHIP_TYPE)

    user = models.ForeignKey(User, related_name="memberships", on_delete=models.CASCADE)
    membership_type = models.TextField(choices=MEMBERSHIP_TYPES, default=DEFAULT_MEMBERSHIP_TYPE)
    started = models.IntegerField(default=this_year)
    until = models.IntegerField(default=this_year)
    honorary = models.BooleanField(default=False)

    #  paid = models.BooleanField(default=False)  # Issue #63: Removed

    def is_membership_type_invoice(membership_type: str) -> bool:
        return "INVOICE" in membership_type

    def is_membership_type_academic(membership_type: str) -> bool:
        return "ACADEMIC" in membership_type

    @property
    def active(self) -> bool:
        return this_year() <= self.until  # Issue #63: Don't use `paid` -- it has been removed

    @classmethod
    def is_member(cls, user: User) -> bool:
        try:
            return cls.get(user=user).active
        except cls.DoesNotExist:
            return False


class Event(Model):
    code = models.TextField(unique=True, default=random_code)  # Show as an input
    title = models.TextField(unique=True, null=False, blank=False)  # Show as an input
    description = models.TextField(blank=True)
    public = models.BooleanField(default=False)
    registration_open = models.DateField(auto_now_add=True, help_text="Date registration opens (inclusive)")
    registration_close = models.DateField(help_text="Date registration closes (inclusive)")
    max_participants = models.PositiveIntegerField(
        default=0,
        help_text="Maximum number of participants to this event (0 = no limit)",
    )
    # Issue #63: Removed this `currency` field (we already have the `currency` field in the `RegistrationOption` model).
    #  currency = models.TextField(null=True, blank=True)  # Show as an input

    # XXX: Do we still leave this payment-related stuff here?
    payment_deadline_days = models.IntegerField(default=30)
    payment_details = models.TextField(blank=True, default="")

    @property
    def can_register(self):
        today = date.today()
        return today >= self.registration_open and today <= self.registration_close

    def get_active_registrations(self):
        """
        Return the active registrations
        """
        return self.registrations.all().filter(REGISTRATION_ACTIVE_QUERY)
        # return self.registrations.all().filter(active=True)

    def get_active_user_registration(self, user: User | None):
        """
        Get the user registration for this event
        """
        # Return empty list if no user has specified or it's a `lazy user` (not from system)
        if not user or not user.id:
            return []
        active_user_registrations = self.registrations.all().filter(REGISTRATION_ACTIVE_QUERY, user=user)
        #  active_user_registrations = self.registrations.all().filter(active=True, user=user)
        if len(active_user_registrations):
            return active_user_registrations[0]
        return None

    def has_active_user_registration(self, user: User | None):
        """
        Has the user registration for this event?
        """
        active_user_registration = self.get_active_user_registration(user)
        return bool(active_user_registration)

    def __unicode__(self):
        # XXX: Is it required (due to existed `__str__` method?
        return self.name

    def clean(self):
        super(Event, self).clean()
        if self.registration_close and self.registration_open and self.registration_open >= self.registration_close:
            raise ValidationError("Registration must open before it closes")

    def in_registration_window(self):
        today = date.today()
        return (today >= self.registration_open) and (not self.registration_close or today <= self.registration_close)

    def new_registration_url(self):
        return reverse("event_registration_new", args=(self.code,))

    def new_registration_full_url(self):
        site = Site.objects.get_current()
        scheme = "https"
        # For dev-server use http
        if settings.LOCAL:
            # TODO: Determine actual protocol scheme
            # Eg, with request: `scheme = 'https' if request.is_secure() else 'http'``
            scheme = "http"
        return scheme + "://" + site.domain + reverse("event_registration_new", args=(self.code,))

    def __str__(self):
        name_items = [
            self.title,
            "({})".format(self.code) if self.code else None,
        ]
        items = [
            " ".join(filter(None, map(str, name_items))),
            # self.created_at.strftime(dateTimeFormat) if self.created_at else None,
        ]
        info = ", ".join(filter(None, map(str, items)))
        return info

    new_registration_full_url.short_description = "Event registration url"


class RegistrationOption(Model):
    SUPPORTED_CURRENCIES = [
        ("USD", "US Dollar"),
        ("CHF", "Swiss Franc"),
        ("EUR", "Euro"),
        ("CAD", "Canadian Dollar"),  # AKA Loonie :)
    ]
    DEFAULT_CURRENCY = SUPPORTED_CURRENCIES[0][0]

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    item = models.TextField(null=False, blank=False)  # Show as an input
    price = models.FloatField(default=0, null=False)
    currency = models.TextField(choices=SUPPORTED_CURRENCIES, null=False, default=DEFAULT_CURRENCY)

    def __str__(self):
        items = [
            self.item,
            "({})".format(self.price) if self.price else None,
        ]
        info = " ".join(filter(None, map(str, items)))
        return info


class Message(Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    message = models.TextField()
    emailed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        items = [
            self.event,
            self.created_at.strftime(dateFormat) if self.created_at else None,
            "emailed" if self.emailed else None,
        ]
        info = ", ".join(filter(None, map(str, items)))
        return info


class Invoice(Model):
    # Docs recommend putting these on the class:
    # https://docs.djangoproject.com/en/5.0/ref/models/fields/#django.db.models.Field.choices
    INVOICE_STATUS = [
        # Can add other possibilities later
        ("CREATED", "Created"),
        ("ISSUED", "Issued"),
        ("PAID", "Paid"),
        ("REFUNDED", "Refunded"),
    ]
    DEFAULT_INVOICE_STATUS = INVOICE_STATUS[0][0]

    INVOICE_TEMPLATES = [
        # Different templates for specific bank accounts and layouts
        ("M-CHF", "Membership - Swiss Francs"),
        ("M-EUR", "Membership - Euros"),
        ("G-USD", "Generic - USD"),
        ("G-CHF", "Generic - CHF"),
        ("G-EUR", "Generic - EUR"),
        ("G-CAD", "Generic - CAD"),
    ]
    DEFAULT_INVOICE_TEMPLATE = "G-USD"  # INVOICE_TEMPLATES[0][0]

    PAYMENT_METHODS = [
        ("STRIPE", "Stripe"),
        ("INVOICE", "Invoice"),
        #  ("WISE", "Wise"),  # Not yet implemented
    ]
    DEFAULT_PAYMENT_METHOD = PAYMENT_METHODS[0][0]  # "STRIPE"

    id = models.AutoField(primary_key=True)

    name = models.TextField(blank=False, default="")
    address = models.TextField(blank=False, default="")

    #  invoice_no = models.IntegerField(primary_key=True)

    payment_method = models.TextField(choices=PAYMENT_METHODS, default=DEFAULT_PAYMENT_METHOD)

    created = models.DateField(auto_now_add=True)
    status = models.TextField(choices=INVOICE_STATUS, default=DEFAULT_INVOICE_STATUS)

    # Includes the various item descriptions, prices, and currencies
    # and any other necessary info
    data = models.JSONField(null=True, blank=True, help_text="JSON object ({...})")  # default=dict

    # The specific form will depend on the template
    template = models.TextField(choices=INVOICE_TEMPLATES, default=DEFAULT_INVOICE_TEMPLATE)

    extra_invoice_text = models.TextField(blank=True, default="")

    # TODO: reg

    @property
    def invoice_no(self):
        """
        Same as the actual invoice number, which normally has the form
        {two-digit-year}{zero-padded four digit number starting from 1}
        """
        if not self.created or not self.id:
            return "NOT-CREATED-YET"
        year_str = self.created.strftime("%y")
        invoice_no = "#{}{:0>4}".format(year_str, self.id)
        return invoice_no

    def __str__(self):
        items = [
            self.invoice_no,
            self.status,
            self.template,
            self.created.strftime(dateFormat) if self.created else None,
        ]
        info = ", ".join(filter(None, map(str, items)))
        return info


# NOTE: A single reusable QuerySet to check if the registration active
REGISTRATION_ACTIVE_QUERY = ~Q(status="WITHDRAWN")


class Registration(Model):
    """
    Ex `Booking` class in OneEvent
    """

    # TODO: Move to the `Registration` data model as a static field?
    REGISTRATION_STATUS = [
        # For schools
        ("SUBMITTED", "Application submitted"),
        ("SELECTED", "Applicant selected"),
        ("WAITLIST", "Applicant wait listed"),
        ("DECLINED", "Applicant declined"),  # Inactive?
        ("PAYMENT_PENDING", "Registered (payment pending)"),
        ("REGISTERED", "Registered"),
        ("WITHDRAWN", "Withdrawn"),  # = Inactive
    ]

    invoice = models.ForeignKey(Invoice, related_name="registrations", on_delete=models.SET_NULL, null=True)
    event = models.ForeignKey(Event, related_name="registrations", on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name="registrations", on_delete=models.CASCADE)

    # Which kind of registration for the event
    option = models.ForeignKey(RegistrationOption, related_name="options", on_delete=models.CASCADE)

    status = models.TextField(choices=REGISTRATION_STATUS)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"],
                condition=REGISTRATION_ACTIVE_QUERY,
                name="Single registration per verified user account",
            )
        ]

    def __str__(self):
        items = [
            self.user.full_name_with_email,
            self.status,
            self.created_at.strftime(dateFormat) if self.created_at else None,
        ]
        info = ", ".join(filter(None, map(str, items)))
        return info


# Issue #63: Temporarily unused
# class DiscountCode(Model):
#     event = models.ForeignKey(Event, on_delete=models.CASCADE)
#     code = models.TextField(default=partial(random_code, length=4))  # Show as an input
#     # pyright: ignore [reportArgumentType]
#     only_registration = models.BooleanField(default=True)
#     percentage = models.IntegerField(help_text="Value as a percentage, like 10", blank=True, null=True)
#     absolute = models.FloatField(help_text="Absolute amount of discount", blank=True, null=True)
#
#     def __str__(self):
#         items = [
#             self.event,
#             self.created_at.strftime(dateTimeFormat) if self.created_at else None,
#         ]
#         info = ", ".join(filter(None, map(str, items)))
#         return info
#
#
# class GroupDiscount(Model):
#     event = models.ForeignKey(Event, on_delete=models.CASCADE)
#     group = models.ForeignKey(Group, on_delete=models.CASCADE)
#     only_registration = models.BooleanField(default=True)
#     percentage = models.IntegerField(help_text="Value as a percentage, like 10", blank=True, null=True)
#     absolute = models.FloatField(help_text="Absolute amount of discount", blank=True, null=True)
#
#     def __str__(self):
#         items = [
#             self.event,
#             "registration only" if self.only_registration else None,
#             self.percentage,
#             self.absolution,
#         ]
#         info = ", ".join(filter(None, map(str, items)))
#         return info
