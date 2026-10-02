# Personal sign commands

The default **Recognize signs** workspace matches your calibrated static hand poses to letters and actions. LSP and LSE are separate personal sample profiles, not pre-trained or linguistically validated alphabet models. Dynamic letters and two-handed signs are not supported.

## Setup

1. Select **Start recognition**. Color and hand analysis are configured automatically in the recognition workspace.
2. Follow **Choose a sign → Teach the pose → Try the action** below the live camera. Select a profile and letter. Show exactly one hand and click **Record current pose** at least three times, varying the pose slightly. The counter shows samples for each hand. Use a reliable alphabet reference for your language when forming the sign.
3. Repeat for N and T. Samples persist locally in Qt's application-data directory as `sign-templates.json`; they are specific to the recorded hand side. Record additional samples for the other hand if needed.
4. Check recognition with actions disabled. Unrecognized or ambiguous poses display `unknown`. Similar fingers or occluded thumbs can still cause mistakes; these thresholds have not been validated on a sign-language dataset.
5. Enable actions. Hold a recognized pose for 0.8 seconds. Release it for at least 0.5 seconds before issuing another command. There is a two-second minimum interval between executions.

Default bindings are N → browser and T → terminal. Change bindings with the action selector; bindings last for the current session. Recording samples disables actions. The browser uses the desktop's default handler; the terminal uses an installed terminal emulator without shell evaluation.

## Kinect depth and performance

Enable both streams and **Extended registration** before capture to use the optional 0.5–2.5 m wrist-distance filter. Missing valid depth rejects the command while this filter is enabled. Wrist depth uses the median of valid values in a small registered neighborhood to reduce isolated invalid pixels; it is not ground-truth finger geometry.

Image reduction occurs before RGB conversion to reduce full-resolution conversion work. The existing latest-frame mailbox and MediaPipe VIDEO tracking remain in use. No measured FPS or accuracy improvement is claimed without hardware testing.

## Adding device actions

`ActionRegistry` in `sign_commands.py` maps letters to named handler functions independently of the matcher. Register a smart-device adapter and bind a letter to its name. Network adapters should use a worker with timeouts rather than blocking the GUI; the current local handlers only launch desktop applications.

This is a personal static-command prototype, not a sign-language translator. A validated alphabet recognizer still requires representative labeled data and evaluation with users of that language.
