"""Isolated parser with a memory ceiling; parent enforces elapsed time."""
import json
import sys
from pathlib import Path

_job = None


def limit_memory():
    global _job
    limit = 384 * 1024 * 1024
    if sys.platform != "win32":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        return
    import ctypes as c
    from ctypes import wintypes as w
    class Basic(c.Structure):
        _fields_ = [("process_time", c.c_int64), ("job_time", c.c_int64), ("flags", w.DWORD),
                    ("min_ws", c.c_size_t), ("max_ws", c.c_size_t), ("active", w.DWORD),
                    ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
    class IO(c.Structure):
        _fields_ = [(name, c.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
    class Extended(c.Structure):
        _fields_ = [("basic", Basic), ("io", IO), ("process_memory", c.c_size_t),
                    ("job_memory", c.c_size_t), ("peak_process", c.c_size_t), ("peak_job", c.c_size_t)]
    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.GetCurrentProcess.restype = w.HANDLE
    _job = kernel.CreateJobObjectW(None, None)
    info = Extended()
    info.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.process_memory = limit
    if not _job or not kernel.SetInformationJobObject(_job, 9, c.byref(info), c.sizeof(info)) or not kernel.AssignProcessToJobObject(_job, kernel.GetCurrentProcess()):
        raise RuntimeError("Cannot establish parser memory boundary")


def main():
    try:
        limit_memory()
        from ai_reliability.ingestion.extraction import extract_in_worker, ExtractionError
        try:
            result = extract_in_worker(Path(sys.argv[1]).read_bytes(), sys.argv[2], sys.argv[3])
            sys.stdout.buffer.write(result.model_dump_json().encode("utf-8"))
        except ExtractionError as exc:
            print(json.dumps({"error": str(exc)}))
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
