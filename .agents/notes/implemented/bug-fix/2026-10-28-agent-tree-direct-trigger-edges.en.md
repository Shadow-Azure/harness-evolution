# Agent Note: Direct trigger connections in the Agent execution graph

Status: implemented

English | [中文](2026-10-28-agent-tree-direct-trigger-edges.md)

## Problem

The Agent execution graph represented each connection between a trigger pill and its target with a permanent stub inside the node plus a Vue Flow edge starting at the Agent box edge. The stub ignored real graph edges, so pills without targets still displayed lines, and the node layer in execution details could hide the real edges. Users could not tell whether a trigger was connected or which pill originated a connection.

## Decision

The layout aggregates actual Agent edges and first problem-card edges by their `h{eventIndex}` / `rep{eventIndex}` handles into `triggerConnections`. Agent nodes create handles only for occupied directions, positioned precisely at the pill's upper or lower boundary, and no longer render stubs. The edge layer sits above node backgrounds while pointer events remain disabled. Problem cards are centered on the pill's x coordinate; additional cards for the same pill stack along one column and chain from the preceding card's handle in the same direction. When a problem card and child Agent share a trigger, the child branch trunk takes the shorter of the card's two horizontal sides and leaves 12px of clearance outside the card so both targets remain traceable to the original pill.

## Alternatives considered

Keeping the stubs and rendering them only when an edge exists would remove dangling lines with a smaller change, but it would retain two geometries for the same connection and preserve seam and layering defects. Baking the pill-to-box segment into every custom edge path would also produce a direct connection, but it would require every edge to understand internal node layout and would enlarge the regression surface across collapsing, zooming, and problem-card combinations. Connecting every card for one pill directly to the same handle creates an overlapping bundle that is harder to read, so cards are chained vertically instead.

## Consequences

Trigger connectivity is now determined entirely by layout data, so every new connection type must occupy the relevant handle during layout. Vertical card stacking can increase graph height, while each pill keeps an independent column; trunk avoidance adds a horizontal detour beside a card when a child branch shares its trigger. Because edges now render above node backgrounds, future node decorations must preserve pointer-event isolation so interactive node content remains usable.
