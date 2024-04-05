# @module models.py
# @changed 2024.03.28, 19:28

import base64
import random
import string
from datetime import date

import requests
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import QuerySet
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Model, Q
from django.urls import reverse
from fpdf import FPDF
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Attachment,
    Disposition,
    FileContent,
    FileName,
    FileType,
    Mail,
)

from dds_registration.core.constants.payments import (
    site_default_currency,
    site_supported_currencies,
)

from .core.constants.date_time_formats import dateFormat
from .core.constants.payments import payment_details_by_currency
from .core.helpers.create_receipt_pdf import create_receipt_pdf_from_payment
from .core.helpers.create_invoice_pdf import create_invoice_pdf_from_payment
from .core.helpers.dates import this_year
from .core.constants.payments import currency_emojis
from .money import get_stripe_amount_for_currency, get_stripe_basic_unit

alphabet = string.ascii_lowercase + string.digits
random_code_length = 8


# NOTE: A single reusable QuerySet to check if the registration active
REGISTRATION_ACTIVE_QUERY = ~Q(status__in=("CANCELLED", "WITHDRAWN", "DECLINED"))


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
        self.sync_email_and_username()
        return super().clean()

    def save(self, *args, **kwargs):
        self.sync_email_and_username()
        return super().save(*args, **kwargs)

    @property
    def is_member(self) -> bool:
        try:
            return Membership.objects.get(user=self).active
        except ObjectDoesNotExist:
            return False

    def __init__(self, *args, **kwargs):
        super(User, self).__init__(*args, **kwargs)
        self._original_email = self.email
        self._original_username = self.username

    def email_user(
        self,
        subject: str,
        message: str,
        html_content: bool = False,
        attachment_content: FPDF | None = None,
        attachment_name: str | None = None,
        from_email: str | None = settings.DEFAULT_FROM_EMAIL,
    ) -> None:
        sg = SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
        message = Mail(
            from_email=from_email,
            to_emails=self.email,
            subject=subject,
            plain_text_content=message,
        )
        if attachment_content is None or attachment_name is None:
            pass
        else:
            attachment = Attachment()
            attachment.file_content = FileContent(base64.b64encode(attachment_content.output()).decode())
            attachment.file_type = FileType("application/pdf")
            attachment.file_name = FileName(attachment_name)
            attachment.disposition = Disposition("attachment")
            message.attachment = attachment
        sg.send(message)


class Payment(Model):
    STATUS = [
        ("CREATED", "Created"),
        ("ISSUED", "Issued"),
        ("PAID", "Paid"),
        ("REFUNDED", "Refunded"),
        ("OBSOLETE", "Obsolete"),  # Payment no longer needed
    ]
    DEFAULT_STATUS = STATUS[0][0]

    METHODS = [
        ("STRIPE", "Credit Card (Stripe - extra fees apply)"),
        ("INVOICE", "Bank Transfer (Invoice)"),
        #  ("WISE", "Wise"),  # Not yet implemented
    ]
    DEFAULT_METHOD = "INVOICE"

    # # User name and address, initialized by user's ones, by default
    # name = models.TextField(blank=False, default="")
    # address = models.TextField(blank=False, default="")
    # extra_invoice_text = models.TextField(blank=True, default="")
    # payment_method = models.TextField(choices=PAYMENT_METHODS, default=DEFAULT_PAYMENT_METHOD)
    # SUPPORTED_CURRENCIES = site_supported_currencies
    # DEFAULT_CURRENCY = site_default_currency
    # currency = models.TextField(choices=SUPPORTED_CURRENCIES, null=False, default=DEFAULT_CURRENCY)

    created = models.DateField(auto_now_add=True)
    updated = models.DateField(auto_now=True)
    status = models.TextField(choices=STATUS, default=DEFAULT_STATUS)

    # Includes the information needed to generate an
    # invoice or a receipt
    data = models.JSONField(help_text="Read-only JSON object", default=dict)

    def mark_paid(self):
        if self.status == "PAID":
            return
        self.status = "PAID"
        if settings.SLACK_WEBHOOK:
            title = self.data['event']['title'] if self.data['kind'] == 'event' else 'membership'
            requests.post(
                url=settings.SLACK_WEBHOOK,
                json={"text": "Payment by {} of {}{} for {}".format(self.data['user']['name'], currency_emojis[self.data['currency']], self.data['price'], title)},
            )
        self.save()

    @property
    def invoice_no(self):
        """
        Same as the actual invoice number, which normally has the form
        {two-digit-year}{zero-padded four digit number starting from 1}
        """
        if not self.id:
            return "NOT-CREATED-YET"
        return "#{}{:0>4}".format(self.created.strftime("%y"), self.id)

    @property
    def account(self):
        return payment_details_by_currency[self.data['currency']]

    @property
    def has_unpaid_invoice(self):
        return self.data['method'] == 'INVOICE' and self.status != "PAID"

    def items(self):
        """Adapt items format for events and membership"""
        pass

    @property
    def title(self):
        if self.data['kind'] == 'membership':
            return ""

    def __str__(self):
        return f"Payment {self.id}"

    def invoice_pdf(self):
        return create_invoice_pdf_from_payment(self)

    def receipt_pdf(self):
        return create_receipt_pdf_from_payment(self)

    def email_invoice(self):
        user = User.objects.get(id=self.data['user']['id'])
        kind = "Membership" if self.data['kind'] == 'membership' else 'Event'
        user.email_user(
            subject=f"DdS {kind} Invoice {self.invoice_no}",
            message=f"Please find attached the requested invoice for {kind.lower()}. Please note that your purchase is not complete until the bank transfer is received.\nIf you have any questions, please contact events@d-d-s.ch.",
            attachment_content=self.invoice_pdf(),
            attachment_name=f"DdS invoice {self.invoice_no}.pdf",
        )

    def email_receipt(self):
        user = User.objects.get(id=self.data['user']['id'])
        kind = "Membership" if self.data['kind'] == 'membership' else 'Event'
        user.email_user(
            subject=f"DdS {kind} Receipt {self.invoice_no}",
            message=f"Thanks! A receipt for your event or membership payment is attached.\nIf you have any questions, please contact events@d-d-s.ch.",
            attachment_content=self.receipt_pdf(),
            attachment_name=f"DdS receipt {self.invoice_no}.pdf",
        )


class MembershipData:
    data = [
        {
            'tag': 'ACADEMIC',
            'label': 'Academic',
            'price': 25,
            'currency': 'EUR',
        },
        {
            'tag': 'NORMAL',
            'label': 'Normal',
            'price': 50,
            'currency': 'EUR',
            'default': True,
        },
        {
            'tag': 'HONORARY',
            'label': 'Honorary',
            'price': 0,
            'currency': 'EUR',
        },
    ]
    default = 'NORMAL'
    available = {'NORMAL', 'ACADEMIC'}

    def __getitem__(self, key: str) -> dict:
        dct = {o['tag']: o for o in self.data}
        return dct[key]

    @property
    def choices(self):
        return [(o['tag'], o['label']) for o in self.data]

    @property
    def public_choice_field_with_prices(self):
        return [(obj['tag'], "{} ({} {})".format(obj['label'], obj['price'], obj['currency'])) for obj in self.data if obj['tag'] in self.available]


MEMBERSHIP_DATA = MembershipData()


class Membership(Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    membership_type = models.TextField(choices=MEMBERSHIP_DATA.choices, default=MEMBERSHIP_DATA.default)

    started = models.IntegerField(default=this_year)
    until = models.IntegerField(default=this_year)
    payment = models.OneToOneField(Payment, on_delete=models.SET_NULL, null=True)

    @property
    def active(self) -> bool:
        return this_year() <= self.until

    def __str__(self):
        items = [
            self.user.full_name_with_email,
            self.get_membership_type_display(),
            self.started,
        ]
        info = ", ".join(filter(None, map(str, items)))
        return info


class Event(Model):
    code = models.TextField(unique=True, default=random_code)  # Show as an input
    title = models.TextField(unique=True, null=False, blank=False)  # Show as an input
    description = models.TextField(blank=False, null=False)
    success_email = models.TextField(blank=False, null=False)
    public = models.BooleanField(default=True)
    registration_open = models.DateField(auto_now_add=True, help_text="Date registration opens (inclusive)")
    registration_close = models.DateField(help_text="Date registration closes (inclusive)")
    refund_window_days = models.IntegerField(default=14, help_text="Number of days before an event that a registration fee can be refunded")
    max_participants = models.PositiveIntegerField(
        default=0,
        help_text="Maximum number of participants (0 = no limit)",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(
                registration_close__gte=models.F("registration_open")
                ),
                name="registration_close_after_open",
            )
        ]

    @property
    def can_register(self):
        today = date.today()
        return today >= self.registration_open and today <= self.registration_close and (not self.max_participants or self.active_registration_count < self.max_participants)

    @property
    def active_registration_count(self):
        return self.registrations.all().filter(REGISTRATION_ACTIVE_QUERY).count()

    def get_active_event_registration_for_user(self, user: User):
        active_user_registrations = list(self.registrations.all().filter(REGISTRATION_ACTIVE_QUERY, user=user))
        if active_user_registrations:
            return active_user_registrations[0]
        return None

    @property
    def url(self):
        return reverse("event_registration", args=(self.code,))

    def __str__(self):
        name_items = [
            self.title,
            "({})".format(self.code) if self.code else None,
        ]
        return " ".join(filter(None, map(str, name_items)))


class RegistrationOption(Model):
    event = models.ForeignKey(Event, related_name="options", on_delete=models.CASCADE)
    item = models.TextField(null=False, blank=False)  # Show as an input
    price = models.FloatField(default=0, null=False)

    SUPPORTED_CURRENCIES = site_supported_currencies
    DEFAULT_CURRENCY = site_default_currency
    currency = models.TextField(choices=SUPPORTED_CURRENCIES, null=False, default=DEFAULT_CURRENCY)

    def __str__(self):
        price_items = [
            self.currency,
            self.price,
        ]
        price = " ".join(filter(None, map(str, price_items))) if self.price else ""
        items = [
            self.item,
            "({})".format(price) if price else None,
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


class Registration(Model):
    REGISTRATION_STATUS = [
        # For schools
        ("SUBMITTED", "Application submitted"),
        ("SELECTED", "Applicant selected"),
        ("WAITLIST", "Applicant wait listed"),
        ("DECLINED", "Applicant declined"),
        ("PAYMENT_PENDING", "Registered (payment pending)"),
        ("REGISTERED", "Registered"),
        ("WITHDRAWN", "Withdrawn"),  # Cancelled by user
        ("CANCELLED", "Cancelled"),  # Cancelled by DdS
    ]

    payment = models.OneToOneField(Payment, on_delete=models.SET_NULL, null=True)
    event = models.ForeignKey(Event, related_name="registrations", on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name="registrations", on_delete=models.CASCADE)
    option = models.OneToOneField(RegistrationOption, on_delete=models.CASCADE)
    status = models.TextField(choices=REGISTRATION_STATUS)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"],
                condition=REGISTRATION_ACTIVE_QUERY,
                name="Single active registration per verified user account",
            )
        ]

    @classmethod
    def active_for_user(cls, user: User) -> QuerySet:
        return cls.objects.filter(REGISTRATION_ACTIVE_QUERY, user=user)

    def complete_registration(self):
        self.status = "REGISTERED"
        self.save()
        self.user.email_user(
            subject=f"Registration for {self.event.title}",
            message=self.event.success_email,
        )

    def __str__(self):
        items = [
            self.user.full_name_with_email,
            self.option,
            self.get_status_display(),
            self.created_at.strftime(dateFormat) if self.created_at else None,
        ]
        info = ", ".join(filter(None, map(str, items)))
        return info
