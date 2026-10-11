// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Mohammad Al-Safadi
//
// app-audio.exe <pid> — captures what one program (and the programs it started) plays, using
// Windows' process loopback (Windows 10 2004 and later), and writes it to stdout as raw PCM:
// 48 kHz, 16-bit, stereo. EchoSub reads it from there; nothing else is written anywhere.
//
// It exits when the program it listens to closes (exit code 7), or when EchoSub stops reading.

#include <windows.h>
#include <audioclient.h>
#include <audioclientactivationparams.h>
#include <mmdeviceapi.h>
#include <wrl/implements.h>

#include <cstdio>
#include <cwchar>
#include <fcntl.h>
#include <io.h>
#include <vector>

using Microsoft::WRL::ClassicCom;
using Microsoft::WRL::ComPtr;
using Microsoft::WRL::FtmBase;
using Microsoft::WRL::Make;
using Microsoft::WRL::RuntimeClass;
using Microsoft::WRL::RuntimeClassFlags;

class Activation : public RuntimeClass<RuntimeClassFlags<ClassicCom>, FtmBase, IActivateAudioInterfaceCompletionHandler> {
public:
    HANDLE done = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    HRESULT result = E_FAIL;
    ComPtr<IAudioClient> client;

    STDMETHOD(ActivateCompleted)(IActivateAudioInterfaceAsyncOperation* operation) override {
        HRESULT activated = E_FAIL;
        ComPtr<IUnknown> unknown;
        result = operation->GetActivateResult(&activated, &unknown);
        if (SUCCEEDED(result)) result = activated;
        if (SUCCEEDED(result)) result = unknown.As(&client);
        SetEvent(done);
        return S_OK;
    }
};

static int fail(const char* step, HRESULT hr, int code) {
    fprintf(stderr, "%s failed: 0x%08lx\n", step, static_cast<unsigned long>(hr));
    return code;
}

int wmain(int argc, wchar_t** argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: app-audio <process id>\n");
        return 2;
    }
    const DWORD pid = wcstoul(argv[1], nullptr, 10);
    HANDLE target = OpenProcess(SYNCHRONIZE, FALSE, pid);
    if (target == nullptr) return fail("OpenProcess", HRESULT_FROM_WIN32(GetLastError()), 3);
    _setmode(_fileno(stdout), _O_BINARY);
    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(hr)) return fail("CoInitializeEx", hr, 3);

    AUDIOCLIENT_ACTIVATION_PARAMS params = {};
    params.ActivationType = AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK;
    params.ProcessLoopbackParams.TargetProcessId = pid;
    params.ProcessLoopbackParams.ProcessLoopbackMode = PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE;
    PROPVARIANT activation = {};
    activation.vt = VT_BLOB;
    activation.blob.cbSize = sizeof(params);
    activation.blob.pBlobData = reinterpret_cast<BYTE*>(&params);

    auto handler = Make<Activation>();
    ComPtr<IActivateAudioInterfaceAsyncOperation> operation;
    hr = ActivateAudioInterfaceAsync(VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK, __uuidof(IAudioClient), &activation,
                                     handler.Get(), &operation);
    if (FAILED(hr)) return fail("ActivateAudioInterfaceAsync", hr, 4);
    WaitForSingleObject(handler->done, INFINITE);
    if (FAILED(handler->result)) return fail("activation", handler->result, 4);

    WAVEFORMATEX format = {};
    format.wFormatTag = WAVE_FORMAT_PCM;
    format.nChannels = 2;
    format.nSamplesPerSec = 48000;
    format.wBitsPerSample = 16;
    format.nBlockAlign = format.nChannels * format.wBitsPerSample / 8;
    format.nAvgBytesPerSec = format.nSamplesPerSec * format.nBlockAlign;

    IAudioClient* client = handler->client.Get();
    hr = client->Initialize(AUDCLNT_SHAREMODE_SHARED,
                            AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_EVENTCALLBACK |
                                AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM,
                            200000, 0, &format, nullptr);  // a 20 ms buffer
    if (FAILED(hr)) return fail("Initialize", hr, 5);
    HANDLE ready = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    hr = client->SetEventHandle(ready);
    if (FAILED(hr)) return fail("SetEventHandle", hr, 5);
    ComPtr<IAudioCaptureClient> capture;
    hr = client->GetService(IID_PPV_ARGS(&capture));
    if (FAILED(hr)) return fail("GetService", hr, 5);
    hr = client->Start();
    if (FAILED(hr)) return fail("Start", hr, 5);

    std::vector<BYTE> silence;
    HANDLE waits[2] = {ready, target};
    for (;;) {
        const DWORD which = WaitForMultipleObjects(2, waits, FALSE, 1000);
        if (which == WAIT_OBJECT_0 + 1) return 7;  // the program closed
        UINT32 waiting = 0;
        while (SUCCEEDED(capture->GetNextPacketSize(&waiting)) && waiting > 0) {
            BYTE* data = nullptr;
            UINT32 frames = 0;
            DWORD flags = 0;
            hr = capture->GetBuffer(&data, &frames, &flags, nullptr, nullptr);
            if (FAILED(hr)) return fail("GetBuffer", hr, 6);
            const size_t bytes = static_cast<size_t>(frames) * format.nBlockAlign;
            const BYTE* out = data;
            if (flags & AUDCLNT_BUFFERFLAGS_SILENT) {
                silence.assign(bytes, 0);
                out = silence.data();
            }
            const size_t written = fwrite(out, 1, bytes, stdout);
            capture->ReleaseBuffer(frames);
            if (written != bytes || fflush(stdout) != 0) return 0;  // EchoSub stopped reading
        }
    }
}
