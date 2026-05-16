#!/usr/bin/env python3
"""extract_ptcgl_qr_debug.py.

Scan an iPhone .MOV file frame-by-frame to extract all visible QR codes,
with rich debugging to help diagnose "no QR found" cases.

Features:
- Prints video metadata (fps, duration, resolution).
- Tries multiple preprocessing variants (gray, CLAHE, unsharp, Otsu/adaptive).
- Tries multiple scales (1.0x / 1.5x / 2.0x) and optional rotations (0/90/180/270).
- Saves annotated debug images (with boxes and variant labels).
- Logs per-frame progress and reasons why strings were rejected by the validator.
- Deduplicates valid Pokémon TCG Live codes in first-seen order using OrderedDict.

Usage:
  python extract_ptcgl_qr_debug.py video.MOV
  # common helpful flags:
  python extract_ptcgl_qr_debug.py video.MOV --debug-dir ./debug_out --debug-first 10 --log-every 10
  python extract_ptcgl_qr_debug.py video.MOV --try-rotations --scales 1.0 1.5 2.0 --stride 1
  python extract_ptcgl_qr_debug.py video.MOV --out codes.txt

Dependencies:
  pip install opencv-python pyzbar numpy


## prereqs
## * works with *.MOV files
"""
# pylint: skip-file
from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from typing import List
from typing import Optional
from typing import Tuple

import cv2
import numpy as np

# Optional fallback
try:
    from pyzbar.pyzbar import decode as pyzbar_decode

    _HAS_PYZBAR = True
except Exception:
    _HAS_PYZBAR = False


# ---------------------- PTCGL code validation -------------------------------

_PTCGL_PATTERNS = [
    re.compile(r"^[A-Z0-9]{3,5}(?:-[A-Z0-9]{3,5}){3}$"),  # XXXX-XXXX-XXXX-XXXX
    re.compile(r"^[A-Z0-9]{3,5}(?:-[A-Z0-9]{3,5}){2}$"),  # XXXX-XXXX-XXXX
    re.compile(r"^[A-Z0-9]{12,25}$"),  # 12–25 alnum, no dashes
]


def is_valid_ptcgl_code(s: str) -> bool:
    s = s.strip().upper()
    if not re.fullmatch(r"[A-Z0-9\-]+", s):
        return False
    return any(p.fullmatch(s) for p in _PTCGL_PATTERNS)


def invalid_reason(s: str) -> str:
    up = s.strip().upper()
    if not re.fullmatch(r"[A-Z0-9\-]+", up):
        return "contains non-alphanumeric/hyphen characters"
    if not any(p.fullmatch(up) for p in _PTCGL_PATTERNS):
        return "does not match expected PTCGL patterns"
    return ""


# ---------------------- Image variants / filters ----------------------------


def to_gray(bgr: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)  # keep 3-channels for OpenCV QR


def clahe_bgr(bgr: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l2 = clahe.apply(l)
    lab2 = cv2.merge([l2, a, b])
    return cv2.cvtColor(lab2, cv2.COLOR_LAB2BGR)


def unsharp_mask(bgr: np.ndarray) -> np.ndarray:
    # Gentle sharpening: unsharp mask
    blur = cv2.GaussianBlur(bgr, (0, 0), sigmaX=1.0, sigmaY=1.0)
    return cv2.addWeighted(bgr, 1.5, blur, -0.5, 0)


def otsu_binarize(bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    return cv2.cvtColor(th, cv2.COLOR_GRAY2BGR)


def adaptive_thresh(bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 5)
    return cv2.cvtColor(th, cv2.COLOR_GRAY2BGR)


def scale_image(bgr: np.ndarray, scale: float) -> np.ndarray:
    if scale == 1.0:
        return bgr
    h, w = bgr.shape[:2]
    return cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)


def rotate_image(bgr: np.ndarray, k: int) -> np.ndarray:
    # k in {0,1,2,3} = 0°, 90°, 180°, 270°
    if k % 4 == 0:
        return bgr
    if k % 4 == 1:
        return cv2.rotate(bgr, cv2.ROTATE_90_CLOCKWISE)
    if k % 4 == 2:
        return cv2.rotate(bgr, cv2.ROTATE_180)
    return cv2.rotate(bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)


# ---------------------- Decoding --------------------------------------------


@dataclass
class QRHit:
    text: str
    points: Optional[np.ndarray]  # Nx2 float32 in original frame coords (not scaled/rotated)
    variant: str  # description of preprocessing variant


class MultiQRDecoder:
    def __init__(self):
        self.detector = cv2.QRCodeDetector()
        self._has_multi = hasattr(self.detector, "detectAndDecodeMulti")

    def _decode_opencv(self, img_bgr: np.ndarray) -> Tuple[List[str], List[np.ndarray]]:
        texts, polys = [], []

        if self._has_multi:
            try:
                ok, decoded_info, points, _ = self.detector.detectAndDecodeMulti(img_bgr)
                if ok and decoded_info:
                    for t, p in zip(decoded_info, points if points is not None else []):
                        if t:
                            texts.append(t)
                            if p is not None:
                                # points shape approx (4,1,2) or (N,2)
                                polys.append(np.array(p).reshape(-1, 2).astype(np.float32))
                            else:
                                polys.append(None)
            except Exception:
                pass

        if not texts:
            try:
                t, p = self.detector.detectAndDecode(img_bgr)
                if t:
                    texts.append(t)
                    polys.append(np.array(p).reshape(-1, 2).astype(np.float32) if p is not None else None)
            except Exception:
                pass

        return texts, polys

    def _decode_pyzbar(self, img_bgr: np.ndarray) -> Tuple[List[str], List[np.ndarray]]:
        texts, polys = [], []
        if not _HAS_PYZBAR:
            return texts, polys
        try:
            for obj in pyzbar_decode(img_bgr):
                if not obj.data:
                    continue
                texts.append(obj.data.decode("utf-8", errors="replace"))
                poly = None
                if obj.polygon:
                    poly = np.array([(p.x, p.y) for p in obj.polygon], dtype=np.float32)
                elif obj.rect:
                    x, y, w, h = obj.rect
                    poly = np.array([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], dtype=np.float32)
                polys.append(poly)
        except Exception:
            pass
        return texts, polys

    def decode_variants(
        self,
        base_bgr: np.ndarray,
        scales: Iterable[float],
        try_rotations: bool,
        filters: Iterable[str],
        save_debug: bool,
        debug_dir: Path,
        frame_idx: int,
        dump_all_variants: bool,
    ) -> List[QRHit]:
        """Try multiple variants; return QRHit list in the *original frame coordinates*."""
        hits: List[QRHit] = []

        filter_funcs = {
            "none": lambda x: x,
            "gray": to_gray,
            "clahe": clahe_bgr,
            "unsharp": unsharp_mask,
            "otsu": otsu_binarize,
            "adaptive": adaptive_thresh,
        }

        h0, w0 = base_bgr.shape[:2]

        for scale in scales:
            scaled = scale_image(base_bgr, scale)
            for filt in filters:
                if filt not in filter_funcs:
                    continue
                img = filter_funcs[filt](scaled)
                for rot_k in [0, 1, 2, 3] if try_rotations else [0]:
                    img_r = rotate_image(img, rot_k)
                    variant_name = f"scale{scale:.2f}_{filt}_rot{rot_k*90}"

                    # Decode via OpenCV first, then fallback to pyzbar
                    texts, polys = self._decode_opencv(img_r)
                    if not texts:
                        t2, p2 = self._decode_pyzbar(img_r)
                        texts += t2
                        polys += p2

                    # Map points back to original frame coords
                    mapped_polys: List[Optional[np.ndarray]] = []
                    for poly in polys:
                        if poly is None:
                            mapped_polys.append(None)
                            continue
                        # Reverse rotation
                        pr = poly.copy()
                        h, w = img_r.shape[:2]
                        if rot_k % 4 == 1:  # 90 cw
                            pr = np.stack([pr[:, 1], w - 1 - pr[:, 0]], axis=1)
                        elif rot_k % 4 == 2:  # 180
                            pr = np.stack([w - 1 - pr[:, 0], h - 1 - pr[:, 1]], axis=1)
                        elif rot_k % 4 == 3:  # 270 cw
                            pr = np.stack([h - 1 - pr[:, 1], pr[:, 0]], axis=1)
                        # Reverse scale
                        pr = pr / scale
                        mapped_polys.append(pr.astype(np.float32))

                    # Save debug images
                    if save_debug and (dump_all_variants or texts):
                        dbg = img_r.copy()
                        # annotate variant
                        cv2.putText(
                            dbg,
                            variant_name,
                            (10, 24),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 0, 255),
                            2,
                            cv2.LINE_AA,
                        )
                        # draw boxes on rotated+scaled image
                        for poly in polys:
                            if poly is None:
                                continue
                            pts = poly.reshape(-1, 2).astype(int)
                            for i in range(len(pts)):
                                cv2.line(dbg, tuple(pts[i]), tuple(pts[(i + 1) % len(pts)]), (0, 255, 0), 2)
                        out_path = debug_dir / f"frame{frame_idx:06d}_{variant_name}.jpg"
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            cv2.imwrite(str(out_path), dbg)
                        except Exception:
                            pass

                    # Record hits
                    for t, mp in zip(texts, mapped_polys):
                        hits.append(QRHit(text=t, points=mp, variant=variant_name))

        return hits


# ---------------------- Video scanning --------------------------------------


def summarize_video(cap: cv2.VideoCapture, path: str, logger: logging.Logger) -> None:
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration = (frame_count / fps) if (fps and frame_count) else 0
    logger.info(f"Opened: {path}")
    logger.info(f"Resolution: {width}x{height} | FPS: {fps:.3f} | Frames: {frame_count} | Duration: {duration:.2f}s")


def scan_video_for_ptcgl_codes(
    video_path: str,
    stride: int,
    max_frames: int,
    scales: Iterable[float],
    try_rotations: bool,
    filters: Iterable[str],
    debug_dir: Optional[Path],
    debug_first: int,
    log_every: int,
    dump_all_variants: bool,
    logger: logging.Logger,
) -> "OrderedDict[str, int]":
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    summarize_video(cap, video_path, logger)
    decoder = MultiQRDecoder()
    unique_codes: "OrderedDict[str, int]" = OrderedDict()

    frame_idx = 0
    processed = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if stride > 1 and (frame_idx % stride) != 0:
            frame_idx += 1
            continue

        # Decide if we write debug for this frame
        save_debug = debug_dir is not None and (processed < debug_first or dump_all_variants)

        # Run the decoding pipeline across variants
        hits = decoder.decode_variants(
            base_bgr=frame,
            scales=scales,
            try_rotations=try_rotations,
            filters=filters,
            save_debug=save_debug,
            debug_dir=debug_dir if debug_dir else Path("."),
            frame_idx=frame_idx,
            dump_all_variants=dump_all_variants,
        )

        # Collate strings (split on whitespace)
        raw_strings: List[Tuple[str, str]] = []  # (text, variant)
        for h in hits:
            if not h.text:
                continue
            for part in re.split(r"[\s\r\n]+", h.text.strip()):
                if part:
                    raw_strings.append((part, h.variant))

        # Validate and record
        accepted_this_frame = 0
        if raw_strings:
            logger.debug(f"[frame {frame_idx}] raw candidate strings: {len(raw_strings)}")
        for raw, variant in raw_strings:
            code = raw.strip().upper()
            if is_valid_ptcgl_code(code):
                if code not in unique_codes:
                    unique_codes[code] = frame_idx
                    logger.info(f"[frame {frame_idx}] ACCEPTED: {code}  (variant={variant})")
                accepted_this_frame += 1
            else:
                reason = invalid_reason(code)
                logger.debug(f"[frame {frame_idx}] rejected '{code}': {reason} (variant={variant})")

        if (processed % max(1, log_every)) == 0:
            logger.info(f"Processed frames: {processed} | Unique valid codes so far: {len(unique_codes)}")

        processed += 1
        frame_idx += 1
        if max_frames > 0 and processed >= max_frames:
            break

    cap.release()
    return unique_codes


# ---------------------- CLI / main ------------------------------------------


def build_logger(verbose: bool) -> logging.Logger:
    logger = logging.getLogger("ptcgl_qr")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    h.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(levelname)s: %(message)s")
    h.setFormatter(fmt)
    # avoid duplicate handlers on re-run
    if logger.handlers:
        logger.handlers.clear()
    logger.addHandler(h)
    return logger


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extract Pokémon TCG Live QR codes from an iPhone .MOV video (with debugging).",
    )
    p.add_argument("video", help="Path to the .MOV file")
    p.add_argument("--stride", type=int, default=1, help="Process every Nth frame (default: 1)")
    p.add_argument("--max-frames", type=int, default=0, help="Stop after this many processed frames (0 = no limit)")
    p.add_argument("--out", type=str, default="", help="Optional path to write codes (one per line)")

    # Debugging controls
    p.add_argument("--verbose", action="store_true", help="Verbose logging (DEBUG level)")
    p.add_argument("--debug-dir", type=str, default="", help="Directory to write annotated debug images")
    p.add_argument(
        "--debug-first",
        type=int,
        default=5,
        help="How many processed frames to dump variants for (default: 5)",
    )
    p.add_argument(
        "--dump-all-variants",
        action="store_true",
        help="Save debug images for all variants even if nothing detected",
    )
    p.add_argument("--log-every", type=int, default=25, help="Log progress every N processed frames (default: 25)")

    # Variant search space
    p.add_argument("--try-rotations", action="store_true", help="Also try 90/180/270° rotations")
    p.add_argument(
        "--scales",
        type=float,
        nargs="+",
        default=[1.0, 1.5, 2.0],
        help="Image scales to try (default: 1.0 1.5 2.0)",
    )
    p.add_argument(
        "--filters",
        type=str,
        nargs="+",
        # default=["none", "gray", "clahe", "unsharp", "otsu", "adaptive"],
        default=["clahe"],
        help="Filters to try: none gray clahe unsharp otsu adaptive",
    )

    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    logger = build_logger(args.verbose)

    debug_dir = Path(args.debug_dir) if args.debug_dir else None
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)

    try:
        codes = scan_video_for_ptcgl_codes(
            video_path=args.video,
            stride=max(1, args.stride),
            max_frames=max(0, args.max_frames),
            scales=args.scales,
            try_rotations=bool(args.try_rotations),
            filters=args.filters,
            debug_dir=debug_dir,
            debug_first=max(0, args.debug_first),
            log_every=max(1, args.log_every),
            dump_all_variants=bool(args.dump_all_variants),
            logger=logger,
        )
    except Exception as e:
        logger.error(f"ERROR: {e}")
        return 1

    # Print final summary
    print("\n=== RESULT ===")
    print(f"Unique valid Pokémon TCG Live codes found: {len(codes)}")
    if codes:
        print("---- Codes (first-seen order) ----")
        for i, (code, first_frame) in enumerate(codes.items(), 1):
            print(f"{i:03d}: {code}  (first seen at frame {first_frame})")

    # Optional file output
    if args.out:
        try:
            with open(args.out, "a", encoding="utf-8") as f:
                for code in codes.keys():
                    f.write(f"{code}\n")
            print(f"\nSaved {len(codes)} code(s) to: {args.out}")
        except Exception as e:
            logger.warning(f"Failed to write '{args.out}': {e}")

    # Guidance when nothing is found
    if len(codes) == 0:
        print("\nNo valid codes found. Debug tips:")
        print("  1) Use --verbose to see rejected strings and reasons.")
        print("  2) Save debug images with --debug-dir ./debug_out (check first 5 frames).")
        print("  3) Try --try-rotations (some MOVs rely on rotation metadata).")
        print("  4) Increase search with --scales 1.0 1.5 2.0 2.5 and keep --filters as default.")
        print("  5) If the QR is tiny/blurry, consider higher scales (2.0–3.0) and unsharp/CLAHE.")
        print("  6) If lighting is harsh, Otsu/adaptive thresholds can help (already enabled).")
        print("  7) If performance is an issue, raise --stride (e.g., 2 or 3) while testing.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


# python extract_ptcgl_qr_debug.py your.MOV   --verbose --try-rotations   --debug-dir ./debug_out --debug-first 10   --scales 1.0 1.5 2.0
