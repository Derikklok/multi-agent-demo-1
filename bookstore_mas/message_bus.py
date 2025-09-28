class MessageBus:
    def __init__(self):
        self._queue = []

    def publish(self, message: dict):
        self._queue.append(message)

    def get_messages(self, msg_type=None):
        if msg_type is None:
            msgs, self._queue = self._queue, []
            return msgs
        msgs = [m for m in self._queue if m.get("type") == msg_type]
        self._queue = [m for m in self._queue if m.get("type") != msg_type]
        return msgs
