import time
import math
import _rpi_ws281x as ws
import atexit

# LED strip common configuration:
LED_FREQ_HZ    = 800000     # Frequency of the LED signal.  We only support 800KHz
LED_BRIGHTNESS = 255        # We manage the brightness in the neopixel library
LED_INVERT     = 0          # We don't support inverted logic

# vector assigning strip instances by the GPIO pin
_led_strips = {}

def neopixel_write(gpio, buf):
    global _led_strips
    strip = None

    # search existing instance at GPIO pin
    if gpio._pin.id in _led_strips:
        strip = _led_strips[gpio._pin.id]

    # WS281x lib only supports /dev/spidev0.0: "For SPI the Raspbian spidev driver is used (/dev/spidev0.0)." (https://pypi.org/project/rpi-ws281x/)
    # Though, channel 13 seems to work on /dev/spidev0.1
    if gpio._pin.id == 21 or gpio._pin.id == 18 or gpio._pin.id == 12:
        spi_channel = 0
    elif gpio._pin.id == 13 or gpio._pin.id == 19:
        spi_channel = 1
    else:
        raise RuntimeError('Selected GPIO not possible: {0}'.format(gpio._pin))

    if strip is None:
        #print("NEW INSTANCE pin: " + str(gpio._pin.id))
        # create new strip instance
        strip = __initStrip(gpio, buf, spi_channel)

        # store instance
        _led_strips[gpio._pin.id] = strip

    channel = ws.ws2811_channel_get(strip, spi_channel)
    # TODO is lib demanding a 1:1 mapping between gpio and spi channel?
    #if gpio._pin.id != ws.ws2811_channel_t_gpionum_get(channel):
        #raise RuntimeError("Raspberry Pi neopixel support is for one strip only!")

    if ws.ws2811_channel_t_strip_type_get(channel) == ws.WS2811_STRIP_RGB:
        bpp = 3
    else:
        bpp = 4
    # assign all colors!
    for i in range(len(buf) // bpp):
        r = buf[bpp*i]
        g = buf[bpp*i+1]
        b = buf[bpp*i+2]
        if bpp == 3:
            pixel = (r << 16) | (g << 8) | b
        else:
            w = buf[bpp*i+3]
            pixel = (w << 24) | (r << 16) | (g << 8) | b
        ws.ws2811_led_set(channel, i, pixel)

    resp = ws.ws2811_render(strip)

    if resp != ws.WS2811_SUCCESS:
        message = ws.ws2811_get_return_t_str(resp)
        raise RuntimeError('ws2811_render failed with code {0} ({1})'.format(resp, message))
    time.sleep(0.001 * ((len(buf)//100)+1))  # about 1ms per 100 bytes


def __initStrip(gpio, buf, spi_channel):
    # Create a ws2811_t structure from the LED configuration.
    # Note that this structure will be created on the heap so you
    # need to be careful that you delete its memory by calling
    # delete_ws2811_t when it's not needed.
    strip = ws.new_ws2811_t()

    if len(_led_strips) == 0:
        # Initialize all channels to off
        for channum in range(2):
            channel = ws.ws2811_channel_get(strip, channum)
            ws.ws2811_channel_t_count_set(channel, 0)
            ws.ws2811_channel_t_gpionum_set(channel, 0)
            ws.ws2811_channel_t_invert_set(channel, 0)
            ws.ws2811_channel_t_brightness_set(channel, 0)
        
    channel = ws.ws2811_channel_get(strip, spi_channel)

    # Initialize the channel in use
    count = 0
    if len(buf) % 3 == 0:
        # most common, divisible by 3 is likely RGB
        strip_type = ws.WS2811_STRIP_RGB
        count = len(buf)//3
    elif len(buf) % 4 == 0:
        strip_type = ws.SK6812_STRIP_RGBW
        count = len(buf)//4
    else:
        raise RuntimeError("We only support 3 or 4 bytes-per-pixel")

    ws.ws2811_channel_t_count_set(channel, count) # we manage 4 vs 3 bytes in the library
    ws.ws2811_channel_t_gpionum_set(channel, gpio._pin.id)
    ws.ws2811_channel_t_invert_set(channel, LED_INVERT)
    ws.ws2811_channel_t_brightness_set(channel, LED_BRIGHTNESS)
    ws.ws2811_channel_t_strip_type_set(channel, strip_type)

    # DMA channels: "the reserved channels should be: 0, 1, 3, 6, 7, 15. The strange thing is that 5 isn’t marked as reserved."
    # see https://github.com/jgarff/rpi_ws281x/issues/224
    # DMA channel will be picked from the range of 8-14 based on the index in strip dictionary
    led_dma_num = 8 + len(_led_strips)

    # Initialize the controller
    ws.ws2811_t_freq_set(strip, LED_FREQ_HZ)
    ws.ws2811_t_dmanum_set(strip, led_dma_num)

    resp = ws.ws2811_init(strip)
    if resp != ws.WS2811_SUCCESS:
        if resp == -5:
            raise RuntimeError("NeoPixel support requires running with sudo, please try again!")
        message = ws.ws2811_get_return_t_str(resp)
        raise RuntimeError('ws2811_init failed with code {0} ({1})'.format(resp, message))
    atexit.register(neopixel_cleanup)
    
    return strip

# based on existing API, all led strips will be flushed
def neopixel_cleanup():
    global _led_strips
    strip = None
    
    if len(_led_strips) > 0:
        for strip in _led_strips.values():
            # Ensure ws2811_fini is called before the program quits.
            ws.ws2811_fini(strip)
            # Example of calling delete function to clean up structure memory.  Isn't
            # strictly necessary at the end of the program execution here, but is good practice.
            ws.delete_ws2811_t(strip)
        
        _led_strips.clear()
