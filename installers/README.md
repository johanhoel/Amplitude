# Installing on Linux

CamWatch, Home Deck and DStreamer run on Linux. One script installs any of
them, on a Debian or Ubuntu machine or a Raspberry Pi:

```bash
curl -fsSL https://raw.githubusercontent.com/johanhoel/amplitude/main/installers/linux/setup.sh | sudo bash -s camwatch
```

Pass `camwatch`, `homedeck` or `dstreamer`. From a checkout, run
[`linux/setup.sh`](linux/setup.sh) directly with the same argument.

## There is no Mac or Windows installer

There was a Mac one, and a Windows one before that. Both are gone on purpose,
and for the same reason.

DStreamer needs direct access to the network card for its PTP clock and its
audio. Windows puts WSL behind a virtual adapter, and the audio arrived with
gaps - roughly 2 ms, several times a minute, which is audible. No setting
closes that, because the clock cannot see the wire. A Mac virtual machine has
the same problem in a milder form.

CamWatch and Home Deck would have worked on either. But keeping those paths
alive for two of three projects meant maintaining installers nobody could test
without the hardware in front of them. The Windows one showed what that costs:
its version gate rejected every machine for a week, because
`[Environment]::OSVersion` reports Windows 8 from inside a ps2exe wrapper.

So: a Linux box or a Raspberry Pi.

## Running Linux on a Mac anyway

Nothing stops you installing Multipass or UTM, giving the machine a **bridged**
network card and running `setup.sh` inside it. CamWatch and Home Deck are fine
that way. DStreamer will have dropouts; that is the milder form of the same
problem, not a setting you have missed.

## Checks

`python3 installers/tests/check.py` reads the script for the things that have
actually broken: CRLF line endings, and a `set` line that does not catch unset
variables or a broken pipe. The `checks` workflow runs it, along with
`bash -n` and shellcheck.
