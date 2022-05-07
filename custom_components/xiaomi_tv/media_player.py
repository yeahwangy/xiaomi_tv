"""Add support for the Xiaomi TVs."""
import logging
import time, datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import (
    SUPPORT_BROWSE_MEDIA,
    SUPPORT_TURN_OFF,
    SUPPORT_TURN_ON,
    SUPPORT_VOLUME_STEP,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_SELECT_SOURCE,
    SUPPORT_SELECT_SOUND_MODE,
    SUPPORT_PLAY_MEDIA,
    SUPPORT_PLAY,
    SUPPORT_PAUSE,
    SUPPORT_NEXT_TRACK,
    SUPPORT_PREVIOUS_TRACK
)
from homeassistant.const import (
    CONF_HOST, 
    CONF_NAME,
    STATE_OFF, 
    STATE_ON, 
    STATE_PLAYING, 
    STATE_PAUSED,
    STATE_UNAVAILABLE
)

from .const import DOMAIN, VERSION
from .utils import keyevent, startapp, check_port, getsysteminfo, changesource, getinstalledapp, capturescreen
from .browse_media import async_browse_media
from .dlna import MediaDLNA
from .adb import MediaADB
from .kodi import MediaKodi

_LOGGER = logging.getLogger(__name__)

SUPPORT_XIAOMI_TV = SUPPORT_VOLUME_STEP | SUPPORT_VOLUME_MUTE | SUPPORT_VOLUME_SET | \
    SUPPORT_TURN_ON | SUPPORT_TURN_OFF | SUPPORT_SELECT_SOURCE | SUPPORT_SELECT_SOUND_MODE | \
    SUPPORT_PLAY_MEDIA | SUPPORT_PLAY | SUPPORT_PAUSE | SUPPORT_PREVIOUS_TRACK | SUPPORT_NEXT_TRACK | \
    SUPPORT_BROWSE_MEDIA

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    host = entry.data.get(CONF_HOST)
    name = entry.data.get(CONF_NAME)
    tv_url = entry.options.get('tv_url', '')
    # 只执行一次
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
        hass.http.register_static_path('/xiaomi_tv-local', hass.config.path("custom_components/xiaomi_tv/www"), False)
        hass.components.frontend.add_extra_js_url(hass, '/xiaomi_tv-local/tv-remote.js?v=' + VERSION)

    async_add_entities([XiaomiTV(host, name, tv_url, hass)], True)

class XiaomiTV(MediaPlayerEntity):
    """Represent the Xiaomi TV for Home Assistant."""

    def __init__(self, ip, name, tv_url, hass):
        """Receive IP address and name to construct class."""
        self.hass = hass
        self.ip = ip
        self._name = name
        self._volume_level = 1
        self._is_volume_muted = False
        self._state = STATE_OFF
        self.is_alive = False
        self._source_list = []
        self._sound_mode_list = ['hdmi1', 'hdmi2', 'hdmi3', 'gallery', 'aux', 'tv', 'vga', 'av', 'dtmb']
        # 直播源
        self.tv_url = tv_url
        # DLNA媒体设备
        self.dlna = MediaDLNA(ip)
        self.adb = MediaADB(ip, self)
        self.kodi = MediaKodi(ip, self)
        # 更新时间
        self.update_at = None
        # 已知应用列表
        self.app_list = []
        self.apps = {}
        # mitv ethernet Mac address
        self._attributes = {}
        # 失败计数器
        self.fail_count = 0

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self.ip.replace('.', '')

    @property
    def volume_level(self):
        return self._volume_level

    @property
    def is_volume_muted(self):
        return self._is_volume_muted

    @property
    def state(self):
        """Return _state variable, containing the appropriate constant."""
        return self._state

    @property
    def assumed_state(self):
        """Indicate that state is assumed."""
        return True

    @property
    def sound_mode_list(self):
        return self._sound_mode_list

    @property
    def source_list(self):
        return self._source_list

    @property
    def media_duration(self):
        return self.dlna.media_duration

    @property
    def media_position(self):
        return self.dlna.media_position

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return SUPPORT_XIAOMI_TV

    @property
    def device_class(self):
        return 'tv'

    @property
    def device_info(self):
        return {
            "identifiers": {
                (DOMAIN, self.unique_id)
            },
            "name": self.name,
            "manufacturer": "Xiaomi",
            "model": self.ip,
            "sw_version": VERSION,
            "via_device": (DOMAIN, self.ip),
        }

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        return await async_browse_media(self, media_content_type, media_content_id)

    # 选择应用
    async def async_select_source(self, source):
        app = self.apps[source]
        if app is not None:
            # 判断是否视频源
            if self.sound_mode_list.count(app) > 0:
                await self.async_select_sound_mode(app)
                return

            # 在选择应用时，先回到首页
            await keyevent(self.ip, 'home')
            time.sleep(1)
            await startapp(self.ip, app)

    # 选择数据源
    async def async_select_sound_mode(self, sound_mode):
        if self.sound_mode_list.count(sound_mode) > 0:
            self.fire_event(sound_mode)
            await changesource(self.ip, sound_mode)

    async def async_turn_off(self):
        if self._state != STATE_OFF:
            await keyevent(self.ip, 'power')
            self.fire_event('off')
            self._state = STATE_OFF

    async def async_turn_on(self):
        if self._state != STATE_ON:
            self.fire_event('on')
            self._state = STATE_ON

    # 发送事件
    def fire_event(self, cmd):
        self.hass.bus.async_fire("xiaomi_tv", { 'entity_id': self.entity_id, 'type': cmd })

    async def async_volume_up(self):
        await keyevent(self.ip, 'volumeup')

    async def async_volume_down(self):
        await keyevent(self.ip, 'volumedown')

    async def async_mute_volume(self, mute):
        if mute:
            await self.async_set_volume_level(0)
        else:
            await self.async_set_volume_level(0.5)
        self._is_volume_muted = mute

    async def async_set_volume_level(self, volume):
        self._volume_level = volume
        # 小米盒子音量最大值15，当音量小于15时，则实际值设置
        if '盒子' in self._attr_media_title:
            if volume <= 0.15:
                arr = [0, 0.05, 0.1, 0.2, 0.25, 0.3, 0.4, 0.45, 0.5, 0.6, 0.65, 0.7, 0.75, 0.85, 0.9, 1]
                volume = arr[int(volume * 100)]
        # 小米电视音量最大值50，当音量小于20时，则实际值设置
        elif '电视' in self._attr_media_title:
            if volume <= 0.2:
                volume = round(volume * 2.0, 2)
        # 调整音量
        await self.dlna.async_set_volume_level(volume)

    async def async_play_media(self, media_type, media_id, **kwargs):
        if self.kodi.state != STATE_UNAVAILABLE:
            await self.kodi.async_play_media(media_type, media_id)
        else:
            await self.dlna.async_play_media(media_type, media_id)

    async def async_media_play(self):
        
        if self.kodi.state != STATE_UNAVAILABLE:
            result = await self.kodi.async_media_play()
        else:
            result = await self.dlna.async_media_play()

        if result:
            self._state = STATE_PLAYING
        else:
            await keyevent(self.ip, 'enter')

    async def async_media_pause(self):
        result = await self.dlna.async_media_pause()
        if result:
            self._state = STATE_PAUSED
        else:
            await keyevent(self.ip, 'enter')

    async def async_media_next_track(self):
        await keyevent(self.ip, 'right')

    async def async_media_previous_track(self):
        await keyevent(self.ip, 'left')

    # 更新属性
    async def async_update(self):
        # 检测当前IP是否在线
        if check_port(self.ip, 6095):
            self.fail_count = 0
        else:
            self.fail_count = self.fail_count + 1
        
        app_len = len(self.app_list)
        if self.fail_count == 0:
            self._state = STATE_PLAYING
            # 同步DLNA状态
            if self.dlna.state != STATE_UNAVAILABLE:
                self._state = self.dlna.state
            # 根据应用列表数量，判断是否初次更新
            if app_len == 0:
                # 获取电视信息
                systeminfo = await getsysteminfo(self.ip)
                if systeminfo is not None:
                    self._attr_media_title = systeminfo['devicename']
                # 获取应用列表
                app_info = await getinstalledapp(self.ip)
                if app_info is not None:
                    for app in app_info:
                        self.apps.update({ app['AppName']: app['PackageName'] })
                
                # 绑定视频源
                for mode in self._sound_mode_list:
                    self.apps.update({ mode.upper(): mode })

                # 绑定数据源
                _source_list = []
                for name in self.apps:
                    _source_list.append(name)
                self.app_list = self._source_list = _source_list
            # 调整扩展服务更新时间
            if self.update_at is None or (datetime.datetime.now() - self.update_at).seconds > 20:
                self.update_at = datetime.datetime.now()
                await self.dlna.async_update()
                await self.adb.async_update()
                await self.kodi.async_update()
            # 获取截图
            res = await capturescreen(self.ip)
            if res is not None:
                self._attr_media_image_url = res['url']
                self._attr_app_id = res['id']
                self._attr_app_name = res['name']

            self.is_alive = True
        elif self.fail_count >= 2:
            self.fail_count = 2
            self.is_alive = False
            self._state = STATE_OFF
            self._attr_media_image_url = None
            if app_len > 0:
                self.app_list = []
            # 关闭服务
            await self.adb.async_turn_off()
            await self.dlna.async_turn_off()