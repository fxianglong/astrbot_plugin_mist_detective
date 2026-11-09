class AstrMessageEvent:
    def __init__(self, text="", messages=None, private=True, sender="10001", platform="qq"):
        self.message_str = text; self._messages = messages or []; self._private = private
        self._sender = sender; self._platform = platform; self.outbox = []; self.stopped = False
        self.unified_msg_origin = f"{platform}:FriendMessage:{sender}"
    def get_messages(self): return self._messages
    def is_private_chat(self): return self._private
    def get_sender_id(self): return self._sender
    def get_platform_id(self): return self._platform
    def get_sender_name(self): return getattr(self, 'name', '群友' + self._sender)
    def plain_result(self, text): return text
    async def send(self, r): self.outbox.append(r)
    def stop_event(self): self.stopped = True

class _Group:
    def command(self, name, alias=None):
        def deco(fn): return fn
        return deco

class filter:
    @staticmethod
    def llm_tool(name=None):
        def deco(fn): return fn
        return deco

    @staticmethod
    def command_group(name, alias=None):
        def deco(fn): return _Group()
        return deco

    @staticmethod
    def command(name, alias=None):
        def deco(fn): return fn
        return deco

class MessageChain:
    def __init__(self): self.text = ""
    def message(self, t): self.text += t; return self
def _file_image(self, p): self.text += f"[图片:{p}]"; return self
MessageChain.file_image = _file_image
def _image_result(self, p): return f"[图片:{p}]"
AstrMessageEvent.image_result = _image_result
def _chain_result(self, chain): return chain
AstrMessageEvent.chain_result = _chain_result
