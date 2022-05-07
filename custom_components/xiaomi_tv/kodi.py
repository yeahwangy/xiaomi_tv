from pykodi import get_kodi_connection, Kodi
from homeassistant.const import (
    STATE_OFF, 
    STATE_ON, 
    STATE_PLAYING, 
    STATE_PAUSED, 
    STATE_IDLE, 
    STATE_UNAVAILABLE
)

from .const import DOMAIN
from .utils import check_port

class MediaKodi():

    def __init__(self, ip, media_player):
        self.ip = ip
        self.port = 8080
        self.username = 'kodi'
        self.password = '123456'
        self.media_player = media_player
        self.kodi = None

    @property
    def state(self):
        return STATE_UNAVAILABLE

    async def async_update(self):
        if check_port(self.ip, self.port) == False:
            return
        try:
            if self.kodi is not None:
                return
            kc = get_kodi_connection(self.ip, self.port, None, self.username, self.password, False, 5)
            await kc.connect()
            self.kodi = Kodi(kc)
        except Exception as ex:
            self.kodi = None
            print(ex)

    async def async_volume_up(self):
        await self.kodi.volume_up()

    async def async_volume_down(self):
        await self.kodi.volume_down()

    async def async_set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        await self.kodi.set_volume_level(int(volume * 100))

    async def async_mute_volume(self, mute):
        """Mute (true) or unmute (false) media player."""
        await self.kodi.mute(mute)

    async def async_media_play_pause(self):
        """Pause media on media player."""
        await self.kodi.play_pause()

    async def async_media_play(self):
        """Play media."""
        if self.state == STATE_PAUSED:
            await self.kodi.play()
            return True
        return False

    async def async_media_pause(self):
        """Pause the media player."""
        await self.kodi.pause()

    async def async_media_next_track(self):
        """Send next track command."""
        await self.kodi.next_track()

    async def async_media_previous_track(self):
        """Send next track command."""
        await self.kodi.previous_track()

    async def async_media_seek(self, position):
        """Send seek command."""
        await self.kodi.media_seek(position)

    async def async_play_media(self, media_type: str, media_id: str):
        await self.kodi.play_file(media_id)

    async def async_turn_off(self):
        self.kodi = None