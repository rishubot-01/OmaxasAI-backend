from rest_framework.throttling import AnonRateThrottle


class GuestAIThrottle(AnonRateThrottle):
    """
    Rate limit for unauthenticated OmaxasAI chat requests.

    The request limit is configured in Django settings:
    REST_FRAMEWORK -> DEFAULT_THROTTLE_RATES
    """

    scope = "assistant_guest"