import hashlib


def normalize(text: str | None) -> str:
    if text is None:
        return ""
    return text.strip()


def compute_fingerprint(title: str, qtype: str, options: str) -> str:
    raw = f"{normalize(title)}|{normalize(qtype)}|{normalize(options)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_options_hash(options: str) -> str:
    return hashlib.sha256(normalize(options).encode("utf-8")).hexdigest()


def parse_options(options: str | None) -> list[str]:
    if not options or not options.strip():
        return []
    return [line.strip() for line in options.split("\n") if line.strip()]
