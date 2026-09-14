"""Translate a displayed ability event into a native button press, never a fee edit."""
from ..engine import Ability


def ability_action(event, owner_by_side, hints_by_owner=None):
    if event.get('kind') != 'ability':
        raise ValueError('expected an ability event')
    # Side orientation must be calibrated by the replay importer, not guessed here.
    owner = owner_by_side[event['side']]
    if type(owner) is not int or owner not in (0, 1):
        raise ValueError('native owner must be 0 or 1')
    hints = (hints_by_owner or {}).get(owner, '-')
    # The website slug and reported fee are intentionally not used as native truth.
    return Ability(owner, hints)
