"""
Dedalus Machine — long-running negotiation agent.

Unlike short-lived agents that return in <5s, a Machine is a persistent
process that holds state across days/weeks, polls for vendor email replies,
reasons about counter-offers, and drives multi-round negotiations autonomously.

The Machine is spawned by the orchestrator as a subprocess and registers
itself in the `active_machines` Supabase table for monitoring.
"""
