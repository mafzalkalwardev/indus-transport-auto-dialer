# Call State Machine

The live call detector centralizes state decisions in `src/detection/call_state_machine.py`.
Evidence modules score DOM, audio, transcript, and timing signals; only `CallStateMachine` transitions state.

## States

- `IDLE`
- `DIALING`
- `RINGING`
- `ANSWER_DETECTED`
- `EARLY_ANALYSIS`
- `HUMAN_CANDIDATE`
- `VOICEMAIL_CANDIDATE`
- `IVR_CANDIDATE`
- `HUMAN`
- `VOICEMAIL`
- `IVR`
- `BUSY`
- `NO_ANSWER`
- `FAILED`
- `ENDED`

## Transitions

| Trigger | From | To |
|---|---|---|
| `start_call` | `IDLE` | `DIALING` |
| `ringing_detected` | `DIALING` | `RINGING` |
| `answer_detected` | `RINGING` | `ANSWER_DETECTED` |
| `begin_analysis` | `ANSWER_DETECTED` | `EARLY_ANALYSIS` |
| `human_candidate` | `EARLY_ANALYSIS` | `HUMAN_CANDIDATE` |
| `voicemail_candidate` | `EARLY_ANALYSIS` | `VOICEMAIL_CANDIDATE` |
| `ivr_candidate` | `EARLY_ANALYSIS` | `IVR_CANDIDATE` |
| `confirm_human` | `HUMAN_CANDIDATE` | `HUMAN` |
| `confirm_voicemail` | `VOICEMAIL_CANDIDATE` | `VOICEMAIL` |
| `confirm_ivr` | `IVR_CANDIDATE` | `IVR` |
| `busy_detected` | `RINGING` | `BUSY` |
| `ring_timeout` | `RINGING` | `NO_ANSWER` |
| `operator_hangup` | `ANY NON-FINAL` | `ENDED` |

## Fusion Weights

- DOM evidence: 40%
- Audio evidence: 20%
- Speech content: 30%
- Timing patterns: 10%
