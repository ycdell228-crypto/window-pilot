"""Operator-maintained, expiring grants; caller purpose never creates a grant."""
from datetime import datetime, timezone
import json
from pathlib import Path
from .win32 import PilotError


class AccessPolicy:
    def __init__(self, config_path):
        self.path = Path(config_path)

    def check(self, *, access, executable=None, origin=None):
        try:
            cfg = json.loads(self.path.read_text(encoding='utf-8-sig')).get('authorization', {})
            mode = cfg.get('mode', 'legacy_task_scope')
            if mode == 'legacy_task_scope':
                return {'mode': mode, 'human_authorization_verified': False}
            if mode != 'enforced' or not isinstance(cfg.get('grants', []), list):
                raise ValueError()
            now = datetime.now(timezone.utc)
            for grant in cfg.get('grants', []):
                if not isinstance(grant, dict) or grant.get('revoked', False):
                    continue
                expires = datetime.fromisoformat(grant['expires_at'].replace('Z', '+00:00'))
                if expires.tzinfo is None or expires <= now:
                    continue
                scopes = grant.get('access', [])
                if (not isinstance(grant.get('origins', []), list) or
                        not isinstance(grant.get('executables', []), list)):
                    raise ValueError()
                if not isinstance(scopes, list) or (access not in scopes and not (access == 'observe' and any(
                        scope in scopes for scope in ('observe_and_click', 'observe_and_mouse', 'observe_and_control', 'observe_and_foreground')))):
                    continue
                if origin is not None:
                    matched = origin in grant.get('origins', [])
                else:
                    matched = any(Path(candidate).is_absolute() and
                                  str(Path(candidate).resolve()).casefold() == str(Path(executable).resolve()).casefold()
                                  for candidate in grant.get('executables', []))
                if matched:
                    return {'mode': mode, 'grant_id': str(grant.get('id', '')),
                            'expires_at': expires.isoformat(), 'human_authorization_verified': False}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise PilotError('ACCESS_POLICY_UNAVAILABLE_OR_INVALID: no automatic fallback') from None
        raise PilotError('APPLICATION_ACCESS_NOT_GRANTED: operator grant missing, expired or revoked')
