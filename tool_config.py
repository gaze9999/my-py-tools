"""Small UTF-8 .env reader shared by the local tooling suite."""
import re
from pathlib import Path


class ToolConfig:
    def __init__(self, env_file=None):
        self.file = (Path(env_file) if env_file is not None else Path(__file__).with_name('.env')).resolve()
        self.values = {}
        if not self.file.is_file():
            if env_file is not None:
                raise ValueError(f'Environment file not found: {self.file}')
            return
        for number, line in enumerate(self.file.read_text(encoding='utf-8-sig').splitlines(), 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, separator, value = line.partition('=')
            key, value = key.strip(), value.strip()
            if not separator or not re.fullmatch(r'TOOL_[A-Z0-9_]+', key):
                raise ValueError(f'Invalid setting at {self.file}:{number}')
            if key in self.values:
                raise ValueError(f'Duplicate setting {key} at line {number}')
            if value.startswith(('"', "'")):
                if len(value) < 2 or value[-1] != value[0]:
                    raise ValueError(f'Unclosed quoted setting at line {number}')
                value = value[1:-1]
            self.values[key] = value

    def value(self, key):
        value = self.values.get(key)
        if not value:
            raise ValueError(f'Missing {key}; configure {self.file} or supply its CLI override')
        return value

    def path(self, key, override=None):
        # 命令列路徑沿用工作目錄，設定檔路徑相對於設定檔本身
        if override is not None:
            return Path(override).resolve()
        value = Path(self.value(key))
        return (value if value.is_absolute() else self.file.parent / value).resolve()

    def namespace(self):
        value = self.value('TOOL_HISTORY_NAMESPACE')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', value):
            raise ValueError('Invalid TOOL_HISTORY_NAMESPACE')
        return value
