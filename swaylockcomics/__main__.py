#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
from subprocess import call
from PIL import Image, ImageDraw, ImageFilter
import re
import glob
from random import randint
import inspect
import shutil
import requests
from swaylockcomics._args import args as args
from swaylockcomics._printv import printv, printd
import swaylockcomics._getcomics as _getcomics
from swaylockcomics._check_network import internet_available as internet_available
from swaylockcomics._screen import get_screens_info, get_wayland_outputs
import swaylockcomics._timing
import hashlib


def download_file(link, strip):
    if link[0:4] != "http":
        link = "https://{}".format(link)
    try:
        with requests.get(link, stream=True, timeout=(1, 3)) as r:
            r.raise_for_status()
            with open(strip, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    # If you have chunk encoded response uncomment if
                    # and set chunk_size parameter to None.
                    f.write(chunk)
        return True
    except requests.exceptions.ConnectionError:
        return False


def copy_fallback_xkcd():
    """
    Check if the fallback strip is in the temp-folder. If it's not,
    copy the original from the module folder.
    If the file is present, do a checksum comparison of both files, and
    if the temp-file deviates, replace it with the original.
    """
    global sysdir, cachedir
    sys_xkcd = "{}/xkcd.png".format(sysdir)
    cache_xkcd = "{}/temp/xkcd.png".format(cachedir)
    if not os.path.exists(cache_xkcd) or not md5(sys_xkcd) != md5(cache_xkcd):
        call(["cp", sys_xkcd, cache_xkcd])


def md5(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def clean_cache():
    """Maintain all the cached strips, keep max 5 strips at a time"""
    printv("Removing non-jpg-files...")
    all_strips_files = glob.glob("{}/strips/*".format(cachedir))
    for file in all_strips_files:
        if ".jpg" not in file:
            printv("Deleting `{}`".format(file))
            os.remove(file)
    # Only keep the 5 newest files
    printv("Keeping only the five last images...")
    all_strips_files = sorted(all_strips_files, key=sort_filename_by_date, reverse=True)
    printd("Found {} images in `all_strips_files`".format(len(all_strips_files)))
    if len(all_strips_files) > 5:
        clean_number = len(all_strips_files) - 5
        printd(
            "number of images in `all_strips_files`: {}".format(len(all_strips_files))
        )
        printd("clean_number: {}".format(clean_number))
        for file in all_strips_files[4:-1]:
            printd("Deleting this file: {}".format(file))
            os.remove(file)


def delete_cache():
    """Remove all cached strips"""
    printv("Removing all files in cache...")
    all_strips_files = glob.glob("{}/strips/*".format(cachedir))
    for file in all_strips_files:
        printv("Deleting `{}`".format(file))
        os.remove(file)


def sort_filename_by_date(filename):
    """
    Dirty hack but ok:
    Get a date from a filename in a highly specific format that
    this script makes and return it
    """
    try:
        _date = re.search(r".*-(\d{4})-(\d{2})-(\d{2}).*", filename)
        year = _date.group(1)
        month = _date.group(2)
        day = _date.group(3)
        return year, month, day
    except AttributeError:
        return (str(0), str(0), str(0))


# Start by showing the status of arguments
printd("These arguments are used:")
printd(vars(args))

# Create necessary folders
cachedir = os.path.expanduser("~/.cache/swaylockcomics")
if not os.path.exists(cachedir):
    call(["mkdir", cachedir])
printv("Setting script directory to '{}'".format(cachedir))
sysdir = os.path.dirname(os.path.realpath(__file__))
printv("Getting sys-directory: '{}'".format(sysdir))
temp_folder = "{}/temp".format(cachedir)
if not os.path.exists(temp_folder):
    call(["mkdir", temp_folder])

# Copying the XKCD fallback comic to .cache-folder
copy_fallback_xkcd()


if args.clean_cache:
    clean_cache()
    sys.exit()

if args.delete_cache:
    delete_cache()
    sys.exit()

# Before _ANYTHING_, we check that `swaylock`, `maim` and `curl` is
# installed
check_swaylock = call(
    ["which", "swaylock"], stdout=open(os.devnull, "w"), stderr=open(os.devnull, "w")
)
check_maim = call(
    ["which", "maim"], stdout=open(os.devnull, "w"), stderr=open(os.devnull, "w")
)
check_curl = call(
    ["which", "curl"], stdout=open(os.devnull, "w"), stderr=open(os.devnull, "w")
)
if check_swaylock == 1:
    raise Exception(
        "Could not find that `swaylock` is installed. Please "
        "make sure that this is installed as it is required"
        " for `swaylockcomics` to run."
    )
if check_maim == 1:
    raise Exception(
        "Could not find that `maim` is installed. Please "
        "make sure that this is installed as it is required"
        " for `swaylockcomics` to run."
    )
if check_curl == 1:
    raise Exception(
        "Could not find that `curl` is installed. Please "
        "make sure that this is installed as it is required"
        " for `swaylockcomics` to run."
    )


# Detect connected Wayland/DRM outputs (works without xrandr)
wayland_outputs = get_wayland_outputs()
if wayland_outputs:
    printd("Detected outputs: {}".format([o["name"] for o in wayland_outputs]))
else:
    printd("No Wayland outputs detected from DRM sysfs; will use composite capture")

max_screen_estate = 0.8


def is_valid_image(path):
    """Validate an image using Pillow (imghdr is deprecated in Python 3.13)."""
    try:
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


def _calc_strip_size(img_w, img_h, canvas_w, canvas_h):
    """Scale img to fit within max_screen_estate of canvas, with 1.75x upscale first."""
    mw = int(canvas_w * max_screen_estate)
    mh = int(canvas_h * max_screen_estate)
    img_w = int(img_w * 1.75)
    img_h = int(img_h * 1.75)
    ratio = min(mw / img_w, mh / img_h)
    if ratio < 1:
        img_w = int(img_w * ratio)
        img_h = int(img_h * ratio)
    return img_w, img_h


def screenshot(strip=False, old_strip=False, multi_mode="single"):
    """
    Capture screen(s), apply background filter, paste comic strip(s).
    Returns a str path (single output) or dict {output_name: path} (multi).
    Uses grim -o OUTPUT for per-output captures so swaylock gets correct
    per-monitor images.
    """

    def bg_obfuscation(image_in, tmp_path):
        image_in_w = image_in.size[0]
        image_in_h = image_in.size[1]
        if "pixel" in args.filter:
            if args.filter == "pixel":
                pixel_size = 0.1
                pixel_radius = 10
            elif args.filter == "morepixel":
                pixel_size = 0.05
                pixel_radius = 20
            image_in_w = int(float(image_in.size[0] * pixel_size))
            image_in_h = int(float(image_in.size[1] * pixel_size))
            image_in.save(tmp_path)
            image_in = image_in.resize((image_in_w, image_in_h), Image.BOX)
            image_in_w = int(float(image_in_w * pixel_radius))
            image_in_h = int(float(image_in_h * pixel_radius))
            image_in = image_in.resize((image_in_w, image_in_h), Image.BOX)
        elif "blur" in args.filter:
            if args.filter == "blur":
                blur_radius = 10
            elif args.filter == "moreblur":
                blur_radius = 20
            image_in = image_in.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        elif "gradient" in args.filter:
            image_draw = ImageDraw.Draw(image_in)
            left_color = 32
            right_color = 128
            image_in_s = image_in_w / (right_color - left_color)
            for x in range(right_color - left_color):
                image_draw.rectangle(
                    [(x * image_in_s, 0), ((x + 1) * image_in_s - 1, image_in_h)],
                    fill=f"#{x:02x}{x:02x}{x:02x}",
                )
        elif "solid" in args.filter:
            image_draw = ImageDraw.Draw(image_in)
            image_draw.rectangle([(0, 0), (image_in_w, image_in_h)], fill="#202020")
        return image_in

    def _paste_comic(canvas, strip_path, save_strip=True):
        """Center-paste a comic on canvas using actual canvas dimensions."""
        if not strip_path or not os.path.exists(strip_path):
            return canvas
        cw, ch = canvas.size
        try:
            img = Image.open(strip_path)
        except Exception:
            return canvas
        new_w, new_h = _calc_strip_size(img.size[0], img.size[1], cw, ch)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS).convert("RGB")
        if save_strip:
            img.save(strip_path)
        canvas.paste(img, ((cw - new_w) // 2, (ch - new_h) // 2))
        return canvas

    def _capture_output(out_name, tmp_path):
        """Capture one output via grim (or maim for X11 fallback)."""
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        if out_name == "__composite__":
            if shutil.which("grim"):
                call(["grim", tmp_path])
            else:
                call(["maim", tmp_path])
        else:
            call(["grim", "-o", out_name, tmp_path])
        if not os.path.exists(tmp_path):
            return None
        try:
            return Image.open(tmp_path)
        except Exception:
            return None

    swaylockcomics._timing.midlog("Starting `{}`".format(inspect.stack()[0][3]))

    # Decide which outputs to capture
    if multi_mode in ("mirror", "per-screen") and len(wayland_outputs) > 1:
        targets = wayland_outputs
    elif wayland_outputs:
        targets = wayland_outputs[:1]
    else:
        targets = [{"name": "__composite__", "width": 1920, "height": 1080}]

    results = {}
    for out_info in targets:
        out_name = out_info["name"]
        tmp_path = "{}/out_{}.png".format(temp_folder, out_name.replace("/", "_"))
        raw_img = _capture_output(out_name, tmp_path)
        # Fall back to full composite if per-output capture failed
        if raw_img is None and out_name != "__composite__":
            raw_img = _capture_output("__composite__", tmp_path)
        if raw_img is None:
            fallback = "{}/xkcd.png".format(temp_folder)
            if os.path.exists(fallback):
                shutil.copyfile(fallback, tmp_path)
                raw_img = Image.open(tmp_path)
            else:
                continue

        canvas = bg_obfuscation(raw_img, tmp_path)

        # Choose which strip to paste on this output
        if multi_mode == "per-screen" and isinstance(strip, dict):
            strip_path = strip.get(out_name, strip.get(next(iter(strip), None)))
        else:
            strip_path = strip if isinstance(strip, str) else None

        if strip_path:
            canvas = _paste_comic(canvas, strip_path, save_strip=(old_strip is False))
        canvas.save(tmp_path)
        results[out_name] = tmp_path

    swaylockcomics._timing.midlog("`{}` done".format(inspect.stack()[0][3]))
    if not results:
        raise RuntimeError("screenshot() produced no output")
    if len(results) == 1:
        return next(iter(results.values()))
    return results


def main():
    global args, _getcomics
    now = _getcomics.now
    # Set folder for the images saved by the script
    strips_folder = "{}/strips/".format(cachedir)
    if not os.path.exists(strips_folder):
        call(["mkdir", strips_folder])
    backup_strip = _getcomics.get_backup_strip(args.comic, cachedir, sysdir)

    # Only print a list over available comics
    if args.list_comics:
        # Do a test of all the comics
        if args.test:
            for comic in _getcomics.comics():
                link = _getcomics.comics(comic)["link"]
                print("{}: {}".format(comic, link))
            sys.exit()
        _getcomics.print_comic_list()
        sys.exit()

    # Fetch the newest comic, either the chosen one or a random one
    swaylockcomics._timing.midlog("Getting comic...")
    if not args.comic:
        args.comic = _getcomics.comics()[randint(0, len(_getcomics.comics()) - 1)]
        printv("Comic not chosen, but randomly chose `{}`".format(args.comic))

    # Get comic info (link, date, etc.) - only call once for consistency
    if internet_available:
        _comics_in = _getcomics.comics(comic=args.comic)
        link = _comics_in.get("link", False)
        extra_info = _comics_in.get("extra_info", "")
        # For calvinandhobbes, use the actual comic date in filename
        if args.comic == "calvinandhobbes" and _comics_in.get("comic_date"):
            comic_date = _comics_in["comic_date"]
            printv("Using Calvin and Hobbes comic date: {}".format(comic_date))
        else:
            comic_date = now
        printv("Comics info returned: {}".format(_comics_in))
    else:
        link = False
        extra_info = ""
        comic_date = now

    # Set filename for comic strip to be saved
    if args.xkcd_no_alttext is True:
        strip = "{}{}{}-{}.jpg".format(
            strips_folder, args.comic, "-alttext", comic_date
        )
    else:
        strip = "{}{}-{}.jpg".format(strips_folder, args.comic, comic_date)
    # If filename exists, and it is a valid image file, use that
    # instead of redownloading
    if os.path.exists(strip):
        printv("Strip already exists...")
        if not is_valid_image(strip):
            printv("...and something is wrong with it. Redownloading.")
            try:
                os.remove(strip)
            except Exception:
                pass
        else:
            printv("...and it is good! Using that file instead of " "redownloading.")
            _res = screenshot(strip=strip, old_strip=True, multi_mode=args.multi_mode)
            if isinstance(_res, dict):
                _cmd = ["swaylock"]
                for _out, _p in _res.items():
                    _cmd += ["-i", "{}:{}".format(_out, _p)]
                call(_cmd)
            else:
                call(["swaylock", "-i", _res])
            sys.exit()
    printv(
        "Comic: {}\nGot link: {}\nGot `extra_info`: {}".format(
            args.comic, link, extra_info
        )
    )

    # Make a failsafe in case it can't fetch a comic strip at all
    if link is False:
        printv("Comic returns `False` in link. Using XKCD-fallback strip")
        strip = backup_strip
    else:
        swaylockcomics._timing.midlog("Starting check comic or download")
        # ...but if all is ok, continue.
        # Check to see if the latest comic is already in place
        if not os.path.exists(strip):
            dl_comic = download_file(link, strip)
            if dl_comic is False:
                # First try earlier dates
                i = 0
                while dl_comic is False:
                    i += 1
                    link = eval("get_{}(days={})[0]".format(args.comic, i))
                    now = eval("get_{}(days={})[1]".format(args.comic, i))
                    strip = "{}{}-{}.png".format(strips_folder, args.comic, now)
                    dl_comic = download_file(link, strip)
                    # We will only try three times before giving up
                    if i == 3:
                        strip = backup_strip
                        break

            if args.comic == "xkcd":
                printd("Getting xkcd")
                if args.xkcd_no_alttext is True:
                    printd("...but no alt-text")
                else:
                    strip = _getcomics.xkcd_alttext(strip, extra_info)
                    printd("...with alt-text")
        swaylockcomics._timing.midlog("Downloaded comic")

    # Run lock file
    if args.test:
        sp = strip if isinstance(strip, str) else next(iter(strip.values()))
        Image.open(sp).show()
    else:
        # Build strip argument for per-screen mode
        if args.multi_mode == "per-screen" and len(wayland_outputs) > 1:
            strips_map = {wayland_outputs[0]["name"]: strip}
            for out_info in wayland_outputs[1:]:
                comic_name = _getcomics.comics()[
                    randint(0, len(_getcomics.comics()) - 1)
                ]
                extra_strip = "{}{}-{}.jpg".format(strips_folder, comic_name, now)
                if not os.path.exists(extra_strip):
                    _info = _getcomics.comics(comic=comic_name)
                    if _info and _info.get("link"):
                        download_file(_info["link"], extra_strip)
                strips_map[out_info["name"]] = (
                    extra_strip if os.path.exists(extra_strip) else strip
                )
            strip_arg = strips_map
        else:
            strip_arg = strip

        result = screenshot(strip=strip_arg, multi_mode=args.multi_mode)
        if isinstance(result, dict):
            cmd = ["swaylock"]
            for output_name, path in result.items():
                cmd += ["-i", "{}:{}".format(output_name, path)]
            call(cmd)
        else:
            call(["swaylock", "-i", result])

    clean_cache()


if __name__ == "__main__":
    main()
