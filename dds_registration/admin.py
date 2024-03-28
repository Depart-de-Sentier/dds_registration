from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.admin import SimpleListFilter
from django.db.models import Q

from .forms import (
    EventAdminForm,
    RegistrationOptionAdminForm,
    InvoiceAdminForm,
    UserAdminForm,
)
from .models import (
    # Issue #63: Temporarily unused
    #  DiscountCode,
    #  GroupDiscount,
    Event,
    Message,
    Registration,
    RegistrationOption,
    User,
    Membership,
    Invoice,
)

# Default registrations (without modifications)
#  admin.site.register(GroupDiscount)
admin.site.register(Message)


class IsRegularUserFilter(SimpleListFilter):
    """
    Regular user custom combined filter
    """

    title = "is_regular_user"
    parameter_name = "is_regular_user"

    def lookups(self, request, model_admin):
        return (
            ("1", "Yes"),
            ("0", "No"),
        )

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.filter(is_staff=False, is_superuser=False)
        if self.value() == "0":
            return queryset.filter(~Q(is_staff=False, is_superuser=False))


class UserAdmin(BaseUserAdmin):
    form = UserAdminForm

    #  # UNUSED: Address has integrated into the base user model
    #  inlines = (ProfileInline,)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "address")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    list_display = [
        "email",
        "first_name",
        "last_name",
        "is_active",
        "is_regular_user",
    ]
    list_filter = [IsRegularUserFilter]
    #  exclude = ['email']
    #  readonly_fields = ['email']

    def is_regular_user(self, user):
        return not user.is_staff and not user.is_superuser

    is_regular_user.short_description = "Regular user"
    is_regular_user.boolean = True

    def get_address(self):
        return self.profile.address

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["username"].label = "Email (username)"
        return form

    #  # TODO: Show only regular users by default?
    #  def changelist_view(self, request, extra_context=None):
    #      ref = request.META.get('HTTP_REFERER', '')
    #      path = request.META.get('PATH_INFO', '')
    #      query = request.META.get('QUERY_STRING', '')
    #
    #      # TODO: Detect if there weren't other parameters for this page
    #      test = ref.split(path)[-1]
    #      ref_default = test and not test.startswith('?')
    #      is_default = not query
    #
    #      if is_default:
    #          q = request.GET.copy()
    #          q.setdefault('is_staff__exact', '0')
    #          return redirect('%s?%s' % (request.path, q.urlencode()))
    #
    #      return super(UserAdmin, self).changelist_view(
    #          request, extra_context=extra_context,
    #      )


#  admin.site.unregister(OriginalUser)  # It's not required here
admin.site.register(User, UserAdmin)


class MembershipAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "started",
        "until",
        "honorary",
        #  "paid",
        "active",
        "membership_type",
    ]


admin.site.register(Membership, MembershipAdmin)


class RegistrationAdmin(admin.ModelAdmin):
    # NOTE: Trying to show non-editable fields (this approach doesn't work)
    readonly_fields = [
        #  "invoice_no",
        "created_at",
        "updated_at",
    ]
    search_fields = [
        # TODO?
        #  'user',  # Unsupported lookup 'icontains' for ForeignKey or join on the field not permitted.
        #  'event',
        #  'options',  # Unsupported lookup 'icontains' for ForeignKey or join on the field not permitted.
    ]

    list_display = [
        "user_column",
        "invoice",
        "event",
        "options_column",
        "status",
        "created_at",
    ]

    def user_column(self, reg):
        user = reg.user
        name = user.full_name_with_email
        return name

    user_column.short_description = "User"
    user_column.admin_order_field = "user"

    def options_column(self, reg):
        return ", ".join([p.item for p in [reg.option]])
        #  return ", ".join([p.item for p in reg.options.all()])

    options_column.short_description = "Option"
    options_column.admin_order_field = "option"


admin.site.register(Registration, RegistrationAdmin)


class RegistrationOptionAdmin(admin.ModelAdmin):
    form = RegistrationOptionAdminForm
    search_fields = [
        "item",
        #  'event',  # NOTE: Unsupported lookup 'icontains' for ForeignKey or join on the field not permitted.
    ]
    list_display = [
        "item",
        "event",
        "price",
        "currency",
    ]


admin.site.register(RegistrationOption, RegistrationOptionAdmin)


class EventAdmin(admin.ModelAdmin):
    # TODO: Show linked options (in columns and in the form)?
    readonly_fields = [
        "registration_open",
        "new_registration_full_url",
    ]
    search_fields = [
        "title",
    ]
    form = EventAdminForm
    list_display = [
        "title",
        "code",
        "max_participants",
        #  "currency",
        "registration_open",
        "registration_close",
        "public",
        "new_registration_full_url",
    ]


admin.site.register(Event, EventAdmin)


class InvoiceAdmin(admin.ModelAdmin):
    form = InvoiceAdminForm
    # TODO: Show related objects: registration, membership etc?
    readonly_fields = [
        "invoice_no",
        "registrations_column",
    ]
    list_display = [
        "invoice_no",
        "status",
        #  "data",
        "template",
        "registrations_column",
        "created",
    ]

    def registrations_column(self, invoice):
        registrations = invoice.registrations.all()
        return "; ".join(filter(None, map(str, registrations)))

    registrations_column.short_description = "Registrations"


admin.site.register(Invoice, InvoiceAdmin)


# Issue #63: Temporarily unused
#  class DiscountCodeAdmin(admin.ModelAdmin):
#      form = DiscountCodeAdminForm
#      list_display = [
#          "event",
#          "code",
#          "percentage",
#          "absolute",
#      ]
#
#
#  admin.site.register(DiscountCode, DiscountCodeAdmin)
