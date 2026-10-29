import os
import sys
import psutil
import ctypes

# Windows process priority class constants
PRIORITY_CLASSES = {
    "IDLE": 0x00000040,         # IDLE_PRIORITY_CLASS (Only runs when CPU is completely idle)
    "BELOW_NORMAL": 0x00004000, # BELOW_NORMAL_PRIORITY_CLASS (Gives games priority, perfectly smooth)
    "NORMAL": 0x00000020,       # NORMAL_PRIORITY_CLASS
    "ABOVE_NORMAL": 0x00008000, # ABOVE_NORMAL_PRIORITY_CLASS (Fast real-time voice transcription)
    "HIGH": 0x00000080,         # HIGH_PRIORITY_CLASS (Maximum responsiveness for real-time voice)
}

def set_process_priority(level: str = "BELOW_NORMAL") -> bool:
    """
    Sets the current process priority on Windows so background translations
    never steal CPU cycles from high-refresh-rate gaming (or boosts for real-time voice).
    """
    if sys.platform != "win32":
        return False

    level_upper = level.upper()
    priority_val = PRIORITY_CLASSES.get(level_upper, PRIORITY_CLASSES["BELOW_NORMAL"])

    try:
        # First attempt via psutil
        p = psutil.Process(os.getpid())
        if level_upper == "IDLE":
            p.nice(psutil.IDLE_PRIORITY_CLASS)
        elif level_upper == "BELOW_NORMAL":
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        elif level_upper == "ABOVE_NORMAL":
            p.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
        elif level_upper == "HIGH":
            p.nice(psutil.HIGH_PRIORITY_CLASS)
        else:
            p.nice(psutil.NORMAL_PRIORITY_CLASS)
        print(f"[Priority] Process priority successfully set to: {level_upper} via psutil")
        return True
    except Exception as e:
        # Fallback to direct Win32 API
        try:
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            success = ctypes.windll.kernel32.SetPriorityClass(handle, priority_val)
            if success:
                print(f"[Priority] Process priority set to: {level_upper} via Win32 API")
                return True
            else:
                print(f"[Priority] Failed to set priority class, error code: {ctypes.GetLastError()}")
                return False
        except Exception as win_err:
            print(f"[Priority] Failed to set priority class: {win_err}")
            return False

def apply_thread_limits(max_threads: int = 2) -> None:
    """
    Enforces thread limits on OpenMP, MKL, and CTranslate2 so AI inference
    doesn't spin up across all CPU cores, preserving system responsiveness.
    """
    threads_str = str(max_threads)
    os.environ["OMP_NUM_THREADS"] = threads_str
    os.environ["MKL_NUM_THREADS"] = threads_str
    os.environ["OPENBLAS_NUM_THREADS"] = threads_str
    os.environ["VECLIB_MAXIMUM_THREADS"] = threads_str
    os.environ["NUMEXPR_NUM_THREADS"] = threads_str

    # OpenMP and MKL thread env vars limit worker threads for CTranslate2 and linear algebra libraries
    print(f"[Priority] AI inference threads capped to: {max_threads}")

