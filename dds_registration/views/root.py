# @module views
# @changed 2024.03.25, 16:07

import logging
import traceback

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest
from django.shortcuts import redirect, render

from ..core.helpers.errors import errorToString

from ..models import REGISTRATION_ACTIVE_QUERY, Event, Registration
from .helpers import get_events_list

LOG = logging.getLogger(__name__)


def index(request: HttpRequest):
    try:
        user = request.user
        # Get active and available public events list...
        public_events_data = []
        public_events = Event.objects.filter(public=True)
        for event in public_events:
            # Only if registration has open...
            if event.can_register:
                registration = event.get_active_user_registration(user)
                data = {
                    "event_code": event.code,
                    "event": event,
                    "registration": registration,
                    "user_has_registration": bool(registration),
                }
                public_events_data.append(data)
        # Get the list of events with user's registrations...
        user_events_data = []
        user_registrations = (
            Registration.objects.filter(REGISTRATION_ACTIVE_QUERY, user=user) if user.is_authenticated else []
        )
        #  user_registrations = Registration.objects.filter(user=user, active=True) if user.is_authenticated else []
        for registration in user_registrations:
            event = registration.event
            data = {
                "event_code": event.code,
                "event": event,
                "registration": registration,
                "user_has_registration": True,
            }
            user_events_data.append(data)
        context = {
            "public_events_data": public_events_data,
            "user_events_data": user_events_data,
        }
        debug_data = {
            "public_events_data": public_events_data,
            "user_events_data": user_events_data,
            "user_registrations": user_registrations,
            "context": context,
        }
        # LOG.debug("Render landing", debug_data)
        return render(request, "dds_registration/index.html.django", context)
    except Exception as err:
        sError = errorToString(err, show_stacktrace=False)
        sTraceback = str(traceback.format_exc())
        debug_data = {
            "err": err,
            "traceback": sTraceback,
        }
        LOG.error("Caught error %s (re-raising): %s", sError, debug_data)
        raise err


@login_required
def profile(request: HttpRequest):
    if not request.user.is_authenticated:
        return redirect("index")
    context = {"events_shown": "mine"}
    events = Event.objects.all()  # filter(query).distinct()
    events_list = get_events_list(request, events)
    if events_list and len(events_list):
        context["events"] = events_list
    # else:
    #     messages.info(request, "You don't have any active registrations yet")
    return render(request, "dds_registration/profile.html.django", context)


def components_demo(request: HttpRequest):
    return render(request, "components-demo.html.django")


__all__ = [
    index,
    profile,
    components_demo,
]
