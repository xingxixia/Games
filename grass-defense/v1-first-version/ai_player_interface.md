# Grass Defense AI Player Interface

This game can be used as a simple AI-playable environment.

The AI player receives:

1. A rendered screenshot image of the current game screen.
2. A JSON state object with compact game information.
3. This action interface description.

The AI player should respond with one JSON action, or a list of JSON actions.

## Goal

Win the game by defending all 5 lanes until all waves are defeated.

Avoid letting zombies reach the left side of a lane after that lane's mower has already been used.

## Turn Loop

For each AI turn:

1. Observe `observation.png`.
2. Read `state.json`.
3. Choose one or more actions.
4. Apply the actions.
5. Simulate a short time step.
6. Export a new screenshot and state.

## Coordinate System

- Rows are `0` to `4`, top to bottom.
- Columns are `0` to `8`, left to right.
- Screen coordinates use pixels, with `(0, 0)` at the top-left.

## Recommended Strategy

- Start the game.
- Place `sunflower` early to increase sun income.
- Place `peashooter` or `snowpea` in lanes with zombies.
- Use `wallnut` to delay strong zombies.
- Use `potatomine` as a cheap emergency defense, but remember it needs time to arm.
- Collect visible suns whenever possible.
- Watch card cooldowns and sun cost.

## Action Format

Return JSON like:

```json
{"type": "place_plant", "plant": "peashooter", "row": 2, "col": 1}
```

Or:

```json
[
  {"type": "collect_sun", "index": 0},
  {"type": "place_plant", "plant": "sunflower", "row": 3, "col": 0},
  {"type": "wait", "seconds": 1.0}
]
```

## Available Actions

### Start Game

```json
{"type": "start_game"}
```

### Toggle Pause

```json
{"type": "toggle_pause"}
```

### Select Card

```json
{"type": "select_card", "plant": "sunflower"}
```

Plants:

- `sunflower`
- `peashooter`
- `wallnut`
- `snowpea`
- `potatomine`

### Place Plant

```json
{"type": "place_plant", "plant": "potatomine", "row": 2, "col": 4}
```

### Use Shovel

```json
{"type": "use_shovel", "row": 2, "col": 4}
```

### Collect Sun

Use a visible sun index from `state.suns`.

```json
{"type": "collect_sun", "index": 0}
```

### Click Pixel

Useful when controlling only from screenshot coordinates.

```json
{"type": "click", "x": 500, "y": 300}
```

### Wait

```json
{"type": "wait", "seconds": 1.0}
```

## State Fields

Important fields in `state.json`:

- `sun`: current resource amount
- `wave`: current wave information
- `plants`: placed plants with row, column, HP, and armed state
- `zombies`: visible zombies with row, x-position, HP, type, and slow state
- `suns`: collectible suns with index and screen coordinates
- `cards`: cost, cooldown, and affordability for each card
- `message`: current game message
- `ended` / `won`: game result

## Example AI Policy

1. If game is in menu, use `start_game`.
2. If suns are visible, collect them.
3. If a lane has a zombie and no shooter, place `peashooter` or `snowpea`.
4. If a zombie is close to the house, place `wallnut` or `potatomine`.
5. If sun is high and front lanes are defended, add more `sunflower`.
6. Otherwise wait briefly.
