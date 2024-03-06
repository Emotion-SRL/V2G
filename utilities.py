
import struct


def red_text(text):
    return '\033[91m' + text + '\033[0m'


def teal_text(text):
    return '\033[96m' + text + '\033[0m'


def orange_text(text):
    return '\033[93m' + text + '\033[0m'


def read_UWORD(high_byte, low_byte, scale_factor):
    all_bits = (high_byte << 8) | low_byte
    unsigned_int = struct.unpack('H', all_bits)[0]
    return round(unsigned_int * scale_factor, 1)


def write_UWORD(value, scale_factor=0.1):
    both_bytes = int(value / scale_factor)
    if both_bytes > 0xFFFF:
        print(red_text("In CONVERTING_TO_UWORD: Value too high, setting to 0xFFFF"))
        both_bytes = 0xFFFF
    high_byte = (both_bytes >> 8) & 0xFF
    low_byte = both_bytes & 0xFF
    return high_byte, low_byte


def read_SWORD(high_byte, low_byte, scale_factor):
    return round(((high_byte << 8) | low_byte) * scale_factor, 1)