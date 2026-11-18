"""Cloud save sync: classify, engine, game lock, autosync triggers."""

from morsoul_launcher.sync.classify import Action, classify
from morsoul_launcher.sync.engine import SyncEngine, SyncOutcome, SyncTrigger

__all__ = ["Action", "classify", "SyncEngine", "SyncOutcome", "SyncTrigger"]
