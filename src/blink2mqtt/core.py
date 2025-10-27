from .mixins.helpers import HelpersMixin
from .mixins.mqtt import MqttMixin
from .mixins.topics import TopicsMixin
from .mixins.service import ServiceMixin
from .mixins.blink import BlinkMixin
from .mixins.blink_api import BlinkAPIMixin
from .mixins.refresh import RefreshMixin
from .mixins.loops import LoopsMixin
from .base import Base


class Blink2Mqtt(
    HelpersMixin,
    TopicsMixin,
    ServiceMixin,
    BlinkMixin,
    BlinkAPIMixin,
    RefreshMixin,
    LoopsMixin,
    MqttMixin,
    Base,
):
    pass
