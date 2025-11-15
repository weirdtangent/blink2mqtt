from .mixins.helpers import HelpersMixin
from .mixins.mqtt import MqttMixin
from .mixins.publish import PublishMixin
from .mixins.blink import BlinkMixin
from .mixins.blink_api import BlinkAPIMixin
from .mixins.refresh import RefreshMixin
from .mixins.loops import LoopsMixin
from .base import Base


class Blink2Mqtt(
    HelpersMixin,
    PublishMixin,
    BlinkMixin,
    BlinkAPIMixin,
    RefreshMixin,
    LoopsMixin,
    MqttMixin,
    Base,
):
    pass
