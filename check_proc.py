import psutil
for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'cmdline']):
    try:
        cmd = " ".join(p.info['cmdline'] or [])
        if "run_full_bhadra_sam" in cmd:
            rss_mb = p.info['memory_info'].rss / (1024 * 1024)
            print(f"SAM Process PID {p.info['pid']}: Memory={rss_mb:.1f} MB, Status={p.status()}")
    except Exception as e:
        pass
