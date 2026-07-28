from .base import Base
from .mixins.blink import BlinkMixin
from .mixins.blink_api import BlinkAPIMixin
from .mixins.helpers import HelpersMixin
from .mixins.loops import LoopsMixin
from .mixins.mqtt import MqttMixin
from .mixins.publish import PublishMixin
from .mixins.refresh import RefreshMixin


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
