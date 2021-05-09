import logging
# import gettext
import gkeepapi
import os
import boto3

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import (
    AbstractRequestHandler, AbstractRequestInterceptor, AbstractExceptionHandler)
import ask_sdk_core.utils as ask_utils
from ask_sdk_core.handler_input import HandlerInput

from ask_sdk_model import Response
# from alexa import data

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def get_param_name(name):
    parameter_prefix = 'shopping-list-alexa'
    return f'/{parameter_prefix}/{name}'

client = boto3.client('ssm')
params = client.get_parameters_by_path(
    Path="/shopping-list-alexa", Recursive=True, WithDecryption=True
)["Parameters"]
username = next(item for item in params if item["Name"] == get_param_name("auth-username"))['Value']
note_id = next(item for item in params if item["Name"] == get_param_name("note-id"))['Value']

keep = gkeepapi.Keep()

# first, attempt to resume using master token
try:
    token = client.get_parameter(
        Name=get_param_name('master-token'), WithDecryption=True
    )
    if token:
        logger.info('found master token, attempting to resume')
        # TODO: this operation takes ~5s
        keep.resume(username, token['Parameter']['Value'])
    else:
        logger.info('master token is not truthy')
        raise Exception('master token does not exist')
except:
    logger.info('failed to use master token, re-authenticating')
    password = next(item for item in params if item["Name"] == get_param_name("auth-password"))['Value']

    logger.info('logged in START')
    keep.login(username, password)
    logger.info('logged in END')

    logger.info('store master token START')
    token = keep.getMasterToken()
    client.put_parameter(
        Name=get_param_name('master-token'),
        Description='Cached token for Google Keep authentication',
        Value=token,
        Type='SecureString',
        Overwrite=True
    )
    logger.info('store master token END')

# keep should be ready to use now...


class LaunchRequestHandler(AbstractRequestHandler):
    """Handler for Skill Launch."""

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool

        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response

        return (
            handler_input.response_builder
            .speak('hello')
            .response
        )


class AddItemIntentHandler(AbstractRequestHandler):
    """Handler for Add Item Intent."""

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("AddItemIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        item = ask_utils.get_slot_value(handler_input, 'item')
        if "shopping list" in item:
            return (
                handler_input.response_builder
                .speak("you must specify an item")
                .response
            )

        glist = keep.get(note_id)
        glist.add(item, False, gkeepapi.node.NewListItemPlacementValue.Bottom)
        logger.info('sync START')
        keep.sync()
        logger.info('sync END')

        return (
            handler_input.response_builder
            .speak('added %s to shopping list'%(item))
            # .ask("add a reprompt if you want to keep the session open for the user to respond")
            .response
        )


class HelpIntentHandler(AbstractRequestHandler):
    """Handler for Help Intent."""

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        return (
            handler_input.response_builder
            .speak('help not supported')
            .response
        )


class CancelOrStopIntentHandler(AbstractRequestHandler):
    """Single handler for Cancel and Stop Intent."""

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input) or
                ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input))

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response

        return (
            handler_input.response_builder
            .speak('goodbye not supported')
            .response
        )


class SessionEndedRequestHandler(AbstractRequestHandler):
    """Handler for Session End."""

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response

        # Any cleanup logic goes here.

        return handler_input.response_builder.response


class IntentReflectorHandler(AbstractRequestHandler):
    """The intent reflector is used for interaction model testing and debugging.
    It will simply repeat the intent the user said. You can create custom handlers
    for your intents by defining them above, then also adding them to the request
    handler chain below.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_request_type("IntentRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        _ = handler_input.attributes_manager.request_attributes["_"]
        intent_name = ask_utils.get_intent_name(handler_input)
        speak_output = _("you just triggered {}").format(intent_name)

        return (
            handler_input.response_builder
            .speak(speak_output)
            # .ask("add a reprompt if you want to keep the session open for the user to respond")
            .response
        )


class CatchAllExceptionHandler(AbstractExceptionHandler):
    """Generic error handling to capture any syntax or routing errors. If you receive an error
    stating the request handler chain is not found, you have not implemented a handler for
    the intent being invoked or included it in the skill builder below.
    """

    def can_handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> bool
        return True

    def handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> Response
        logger.error(exception, exc_info=True)

        return (
            handler_input.response_builder
            .speak('error')
            .ask('error')
            .response
        )


# class LocalizationInterceptor(AbstractRequestInterceptor):
#     """
#     Add function to request attributes, that can load locale specific data
#     """

#     def process(self, handler_input):
#         locale = handler_input.request_envelope.request.locale
#         i18n = gettext.translation(
#             'data', localedir='locales', languages=[locale], fallback=True)
#         handler_input.attributes_manager.request_attributes["_"] = i18n.gettext

# The SkillBuilder object acts as the entry point for your skill, routing all request and response
# payloads to the handlers above. Make sure any new handlers or interceptors you've
# defined are included below. The order matters - they're processed top to bottom.


sb = SkillBuilder()

sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(AddItemIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
# make sure IntentReflectorHandler is last so it doesn't override your custom intent handlers
sb.add_request_handler(IntentReflectorHandler())

# sb.add_global_request_interceptor(LocalizationInterceptor())

sb.add_exception_handler(CatchAllExceptionHandler())

handler = sb.lambda_handler()
