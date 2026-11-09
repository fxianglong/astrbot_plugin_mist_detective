import asyncio, functools
SESSIONS = {}
class SessionController:
    def __init__(self): self.future = asyncio.get_event_loop().create_future(); self._timer = None
    def stop(self, error=None):
        if self.future.done(): return
        if self._timer: self._timer.cancel()
        self.future.set_exception(error) if error else self.future.set_result(None)
    def keep(self, timeout=0, reset_timeout=False):
        if self._timer: self._timer.cancel()
        self._timer = asyncio.get_event_loop().call_later(timeout, lambda: (not self.future.done()) and self.future.set_exception(TimeoutError()))
def session_waiter(timeout=30, record_history_chains=False):
    def deco(func):
        @functools.wraps(func)
        async def wrapper(event):
            c = SessionController(); c.keep(timeout)
            SESSIONS[event.unified_msg_origin] = (func, c)
            try: return await c.future
            finally: SESSIONS.pop(event.unified_msg_origin, None)
        return wrapper
    return deco
async def trigger(event):
    func, c = SESSIONS[event.unified_msg_origin]
    try: await func(c, event)
    except Exception as e: c.stop(e)
