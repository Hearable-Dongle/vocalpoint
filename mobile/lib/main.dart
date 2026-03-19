import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:universal_ble/universal_ble.dart';

void main() => runApp(const MyApp());

class AppColors {
  static const Color background = Color(0xFF060606);
  static const Color panel = Color(0xFF0F1012);
  static const Color panelSoft = Color(0xFF16181C);
  static const Color glass = Color(0x66FFFFFF);
  static const Color glassWarm = Color(0x33FF9F1C);
  static const Color outline = Color(0x33FFFFFF);
  static const Color shadow = Color(0x99000000);

  static const Color gold = Color(0xFFFF9F1C);
  static const Color goldBright = Color(0xFFFFB54D);
  static const Color white = Colors.white;
  static const Color muted = Color(0xFFB0B5BD);
  static const Color mutedSoft = Color(0xFF7E838C);
  static const Color success = Color(0xFF2CD280);
  static const Color danger = Color(0xFFFF6B6B);
}

Color shiftLightness(Color color, double delta) {
  final hsl = HSLColor.fromColor(color);
  return hsl.withLightness((hsl.lightness + delta).clamp(0.0, 1.0)).toColor();
}

class AppState {
  // Flip this back to true to restore the original phone-side output scan flow.
  static const bool usePhoneScannedOutputDevices = false;

  static final ValueNotifier<List<RememberedDevice>> rememberedDevices =
      ValueNotifier<List<RememberedDevice>>(<RememberedDevice>[]);

  static final ValueNotifier<String?> connectedDeviceId =
      ValueNotifier<String?>(null);
  static final ValueNotifier<String?> connectedDeviceName =
      ValueNotifier<String?>(null);

  static final ValueNotifier<double> volume = ValueNotifier<double>(50);
  static final ValueNotifier<bool> isMuted = ValueNotifier<bool>(false);
  static final ValueNotifier<Color> highlightColor = ValueNotifier<Color>(
    AppColors.gold,
  );

  static final ValueNotifier<String> bleAddress = ValueNotifier<String>('');
  static final ValueNotifier<String?> audioOutputDeviceName =
      ValueNotifier<String?>(null);
  static final ValueNotifier<List<String>> outputDeviceOptions =
      ValueNotifier<List<String>>(<String>[]);
  static final ValueNotifier<String> param1 = ValueNotifier<String>(
    'Morning Tide',
  );
  static final ValueNotifier<String> param2 = ValueNotifier<String>('');
  static final ValueNotifier<int> voiceProfileNum = ValueNotifier<int>(0);
  static final ValueNotifier<List<VoiceProfileChoice>> voiceProfiles =
      ValueNotifier<List<VoiceProfileChoice>>(<VoiceProfileChoice>[]);

  static final ValueNotifier<String> volumeServiceUuid = ValueNotifier<String>(
    '0000FFFF-0000-1000-8000-00805F9B34FB',
  );
  static final ValueNotifier<String> volumeCharUuid = ValueNotifier<String>(
    '0000FF01-0000-1000-8000-00805F9B34FB',
  );
  static final ValueNotifier<String> metadataCharUuid = ValueNotifier<String>(
    '0000FF02-0000-1000-8000-00805F9B34FB',
  );

  static void clearConnection() {
    connectedDeviceId.value = null;
    connectedDeviceName.value = null;
    outputDeviceOptions.value = <String>[];
    voiceProfiles.value = <VoiceProfileChoice>[];
    voiceProfileNum.value = 0;
    param2.value = '';
  }

  static void clearOutputSelection() {
    bleAddress.value = '';
    audioOutputDeviceName.value = null;
    param1.value = 'Morning Tide';
  }
}

class VoiceProfileChoice {
  final int number;
  final String name;

  const VoiceProfileChoice({required this.number, required this.name});
}

class RememberedDevice {
  final String deviceId;
  final String name;
  final DateTime lastSeen;

  const RememberedDevice({
    required this.deviceId,
    required this.name,
    required this.lastSeen,
  });

  RememberedDevice copyWith({String? name, DateTime? lastSeen}) {
    return RememberedDevice(
      deviceId: deviceId,
      name: name ?? this.name,
      lastSeen: lastSeen ?? this.lastSeen,
    );
  }
}

enum SetupPanel { vocalPoint, output }

enum ControlPanel { volume, mix }

enum ProfileMenuAction { about, systemMetadata, deviceDiagnostics }

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<Color>(
      valueListenable: AppState.highlightColor,
      builder: (context, accent, _) {
        final accentBright = shiftLightness(accent, 0.14);
        final base = ThemeData(
          useMaterial3: true,
          brightness: Brightness.dark,
          colorScheme: ColorScheme.dark(
            primary: accent,
            secondary: accentBright,
            surface: AppColors.panel,
          ),
        );

        return MaterialApp(
          debugShowCheckedModeBanner: false,
          title: 'VocalPoint',
          theme: base.copyWith(
            scaffoldBackgroundColor: AppColors.background,
            textTheme: base.textTheme.apply(
              bodyColor: AppColors.white,
              displayColor: AppColors.white,
            ),
            snackBarTheme: SnackBarThemeData(
              backgroundColor: AppColors.panelSoft.withValues(alpha: 0.95),
              contentTextStyle: const TextStyle(color: AppColors.white),
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(18),
              ),
            ),
            inputDecorationTheme: InputDecorationTheme(
              filled: true,
              fillColor: Colors.white.withValues(alpha: 0.05),
              labelStyle: const TextStyle(color: AppColors.muted),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(18),
                borderSide: BorderSide(
                  color: Colors.white.withValues(alpha: 0.10),
                ),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(18),
                borderSide: BorderSide(
                  color: Colors.white.withValues(alpha: 0.10),
                ),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(18),
                borderSide: BorderSide(color: accent, width: 1.4),
              ),
            ),
          ),
          home: const VocalPointShell(),
        );
      },
    );
  }
}

class VocalPointShell extends StatefulWidget {
  const VocalPointShell({super.key});

  @override
  State<VocalPointShell> createState() => _VocalPointShellState();
}

class _VocalPointShellState extends State<VocalPointShell> {
  static const Duration _panelAnimationDuration = Duration(milliseconds: 480);
  static const Duration _panelIconAnimationDuration = Duration(
    milliseconds: 420,
  );
  static const List<Color> _highlightOptions = <Color>[
    Color(0xFFFF9F1C),
    Color(0xFFFF7A1A),
    Color(0xFFE76F51),
    Color(0xFFE3B545),
  ];

  final List<BleDevice> _vocalPointResults = <BleDevice>[];
  final List<BleDevice> _outputResults = <BleDevice>[];

  late final TextEditingController _serviceUuidController;
  late final TextEditingController _volumeCharUuidController;
  late final TextEditingController _metadataCharUuidController;
  late final VoidCallback _serviceUuidListener;
  late final VoidCallback _volumeCharUuidListener;
  late final VoidCallback _metadataCharUuidListener;

  Timer? _splashStartTimer;
  Timer? _splashFadeTimer;
  Timer? _splashEndTimer;
  Timer? _dashboardTimer;
  Timer? _scanTimeoutTimer;
  Timer? _volumeWriteDebounce;
  Timer? _metadataRefreshTimer;

  bool _showSplashOverlay = true;
  bool _fadeSplashOverlay = false;
  bool _dashboardUnlocked = false;
  bool _isScanning = false;

  SetupPanel? _expandedPanel;
  ControlPanel? _expandedControlPanel;
  SetupPanel? _activeScanTarget;

  String? _pendingVocalPointId;
  String? _pendingOutputId;
  double _lastNonMutedVolume = 50;

  Color get _highlightColor => AppState.highlightColor.value;
  Color get _highlightBright => shiftLightness(_highlightColor, 0.14);

  @override
  void initState() {
    super.initState();
    _serviceUuidController = TextEditingController(
      text: AppState.volumeServiceUuid.value,
    );
    _volumeCharUuidController = TextEditingController(
      text: AppState.volumeCharUuid.value,
    );
    _metadataCharUuidController = TextEditingController(
      text: AppState.metadataCharUuid.value,
    );

    _serviceUuidListener = () => _syncControllerWithNotifier(
      _serviceUuidController,
      AppState.volumeServiceUuid.value,
    );
    _volumeCharUuidListener = () => _syncControllerWithNotifier(
      _volumeCharUuidController,
      AppState.volumeCharUuid.value,
    );
    _metadataCharUuidListener = () => _syncControllerWithNotifier(
      _metadataCharUuidController,
      AppState.metadataCharUuid.value,
    );

    AppState.volumeServiceUuid.addListener(_serviceUuidListener);
    AppState.volumeCharUuid.addListener(_volumeCharUuidListener);
    AppState.metadataCharUuid.addListener(_metadataCharUuidListener);
    AppState.connectedDeviceId.addListener(_handleSetupStateChanged);
    AppState.bleAddress.addListener(_handleSetupStateChanged);

    _configureBleCallbacks();
    _startSplashSequence();
  }

  @override
  void dispose() {
    _splashStartTimer?.cancel();
    _splashFadeTimer?.cancel();
    _splashEndTimer?.cancel();
    _dashboardTimer?.cancel();
    _scanTimeoutTimer?.cancel();
    _volumeWriteDebounce?.cancel();
    _metadataRefreshTimer?.cancel();

    if (_isScanning) {
      UniversalBle.stopScan();
    }
    UniversalBle.onScanResult = null;
    UniversalBle.onConnectionChange = null;

    AppState.connectedDeviceId.removeListener(_handleSetupStateChanged);
    AppState.bleAddress.removeListener(_handleSetupStateChanged);
    AppState.volumeServiceUuid.removeListener(_serviceUuidListener);
    AppState.volumeCharUuid.removeListener(_volumeCharUuidListener);
    AppState.metadataCharUuid.removeListener(_metadataCharUuidListener);

    _serviceUuidController.dispose();
    _volumeCharUuidController.dispose();
    _metadataCharUuidController.dispose();
    super.dispose();
  }

  void _syncControllerWithNotifier(
    TextEditingController controller,
    String value,
  ) {
    if (controller.text == value) return;
    controller.value = controller.value.copyWith(
      text: value,
      selection: TextSelection.collapsed(offset: value.length),
      composing: TextRange.empty,
    );
  }

  void _startSplashSequence() {
    _splashFadeTimer = Timer(const Duration(milliseconds: 520), () {
      if (!mounted) return;
      setState(() => _fadeSplashOverlay = true);
    });

    _splashEndTimer = Timer(const Duration(milliseconds: 820), () {
      if (!mounted) return;
      setState(() => _showSplashOverlay = false);
    });
  }

  void _configureBleCallbacks() {
    UniversalBle.onScanResult = (BleDevice device) {
      if (!mounted || _activeScanTarget == null) return;

      if (_activeScanTarget == SetupPanel.vocalPoint) {
        if (!_hasDisplayName(device) || !_isVocalPointDevice(device)) {
          return;
        }
        _upsertScanResult(_vocalPointResults, device);
      } else {
        if (!_isSelectableOutput(device)) return;
        _upsertScanResult(_outputResults, device);
      }
    };

    UniversalBle.onConnectionChange =
        (String deviceId, bool isConnected, String? error) {
          if (!mounted) return;
          if (AppState.connectedDeviceId.value != deviceId) return;
          if (isConnected) return;

          final disconnectedName =
              AppState.connectedDeviceName.value ?? 'device';
          _stopMetadataRefresh();
          AppState.clearConnection();
          setState(() => _pendingVocalPointId = null);
          _showToast(
            error == null || error.isEmpty
                ? '$disconnectedName disconnected'
                : '$disconnectedName disconnected: $error',
          );
        };
  }

  void _handleSetupStateChanged() {
    final ready = _hasConnectedVocalPoint && _hasSelectedOutputDevice;
    if (ready && !_dashboardUnlocked) {
      setState(() {
        _dashboardUnlocked = true;
        _expandedPanel = null;
        _expandedControlPanel = null;
      });
    }

    if (!ready && _dashboardUnlocked && mounted) {
      setState(() {
        _dashboardUnlocked = false;
        _expandedControlPanel = null;
      });
    }
  }

  Future<void> _skipToDashboard() async {
    if (_isScanning) {
      await _stopScan();
    }
    if (!mounted) return;
    setState(() {
      _dashboardUnlocked = !_dashboardUnlocked;
      if (_dashboardUnlocked) {
        _expandedPanel = null;
        _expandedControlPanel = null;
      } else {
        _expandedControlPanel = null;
      }
    });
  }

  void _toggleControlPanel(ControlPanel panel) {
    setState(() {
      _expandedControlPanel = _expandedControlPanel == panel ? null : panel;
    });
  }

  bool get _hasConnectedVocalPoint => AppState.connectedDeviceId.value != null;
  bool get _hasSelectedOutputDevice {
    if (AppState.usePhoneScannedOutputDevices) {
      return AppState.bleAddress.value.isNotEmpty;
    }

    final selected = AppState.audioOutputDeviceName.value?.trim() ?? '';
    return selected.isNotEmpty;
  }

  bool _hasDisplayName(BleDevice device) {
    final name = device.name?.trim() ?? '';
    return name.isNotEmpty && name != 'Unnamed';
  }

  bool _isSelectableOutput(BleDevice device) {
    return _isNamedDevice(device) && !_isVocalPointDevice(device);
  }

  String _deviceLabel(BleDevice device, {required String fallback}) {
    final name = device.name?.trim() ?? '';
    if (name.isEmpty || name == 'Unnamed' || name == device.deviceId) {
      return fallback;
    }
    return name;
  }

  void _upsertScanResult(List<BleDevice> list, BleDevice device) {
    final index = list.indexWhere((entry) => entry.deviceId == device.deviceId);
    setState(() {
      if (index == -1) {
        list.add(device);
      } else {
        list[index] = device;
      }
    });
  }

  void _showToast(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  void _touchRemembered(String deviceId, String name) {
    final current = List<RememberedDevice>.from(
      AppState.rememberedDevices.value,
    );
    final index = current.indexWhere((entry) => entry.deviceId == deviceId);
    if (index == -1) return;
    current[index] = current[index].copyWith(
      name: name,
      lastSeen: DateTime.now(),
    );
    AppState.rememberedDevices.value = current;
  }

  void _rememberDevice(BleDevice device) {
    final name = _deviceLabel(device, fallback: 'Saved device');
    final current = List<RememberedDevice>.from(
      AppState.rememberedDevices.value,
    );
    final index = current.indexWhere(
      (entry) => entry.deviceId == device.deviceId,
    );

    if (index == -1) {
      current.insert(
        0,
        RememberedDevice(
          deviceId: device.deviceId,
          name: name,
          lastSeen: DateTime.now(),
        ),
      );
    } else {
      current[index] = current[index].copyWith(
        name: name,
        lastSeen: DateTime.now(),
      );
    }
    AppState.rememberedDevices.value = current;
  }

  Future<void> _openPanel(SetupPanel panel) async {
    if (_expandedPanel == panel) {
      if (_activeScanTarget == panel && _isScanning) {
        await _stopScan();
      }
      if (!mounted) return;
      setState(() => _expandedPanel = null);
      return;
    }

    if (_isScanning) {
      await _stopScan();
    }
    if (!mounted) return;
    setState(() => _expandedPanel = panel);
  }

  Future<void> _startScan(SetupPanel panel) async {
    if (_isScanning) {
      await _stopScan();
    }

    setState(() {
      _expandedPanel = panel;
      _activeScanTarget = panel;
      _isScanning = true;
      if (panel == SetupPanel.vocalPoint) {
        _vocalPointResults.clear();
      } else {
        _outputResults.clear();
      }
    });

    try {
      await UniversalBle.startScan();
      _scanTimeoutTimer?.cancel();
      _scanTimeoutTimer = Timer(const Duration(seconds: 10), () => _stopScan());
    } on PlatformException catch (error) {
      _showToast('Scan failed: ${error.code} ${error.message ?? ''}');
      if (mounted) {
        setState(() {
          _isScanning = false;
          _activeScanTarget = null;
        });
      }
    } catch (error) {
      _showToast('Scan failed: $error');
      if (mounted) {
        setState(() {
          _isScanning = false;
          _activeScanTarget = null;
        });
      }
    }
  }

  Future<void> _stopScan() async {
    _scanTimeoutTimer?.cancel();
    try {
      await UniversalBle.stopScan();
    } catch (_) {
      // Ignore stop failures caused by platform state races.
    }
    if (!mounted) return;
    setState(() {
      _isScanning = false;
      _activeScanTarget = null;
    });
  }

  Future<void> _connectToVocalPoint(BleDevice device) async {
    final name = _deviceLabel(device, fallback: 'VocalPoint device');

    setState(() => _pendingVocalPointId = device.deviceId);

    try {
      if (_isScanning) {
        await _stopScan();
      }

      final currentId = AppState.connectedDeviceId.value;
      if (currentId != null && currentId != device.deviceId) {
        try {
          await UniversalBle.disconnect(currentId);
        } catch (_) {
          // Ignore disconnect cleanup errors.
        }
      }

      await UniversalBle.connect(
        device.deviceId,
        connectionTimeout: const Duration(seconds: 10),
      );
      await UniversalBle.discoverServices(device.deviceId);

      AppState.connectedDeviceId.value = device.deviceId;
      AppState.connectedDeviceName.value = name;
      _touchRemembered(device.deviceId, name);
      _rememberDevice(device);

      await _writeVolumeToDevice();
      await _syncSelectedOutputToDevice(showSuccess: false);
      if (AppState.voiceProfiles.value.any(
        (entry) => entry.number == AppState.voiceProfileNum.value,
      )) {
        await _sendVoiceProfileSelection(
          AppState.voiceProfileNum.value,
          showSuccess: false,
        );
      }
      _startMetadataRefresh();
      await _refreshMetadataFromDevice(showErrors: false);

      _showToast('Connected to $name');
    } on PlatformException catch (error) {
      _showToast('Connect failed: ${error.code} ${error.message ?? ''}');
    } catch (error) {
      _showToast('Connect failed: $error');
    } finally {
      if (mounted) {
        setState(() => _pendingVocalPointId = null);
      }
    }
  }

  Future<void> _disconnectVocalPoint() async {
    final deviceId = AppState.connectedDeviceId.value;
    if (deviceId == null) return;

    try {
      await UniversalBle.disconnect(deviceId);
    } catch (_) {
      // Ignore disconnect failures.
    }

    _stopMetadataRefresh();
    AppState.clearConnection();
    if (mounted) {
      setState(() => _pendingVocalPointId = null);
    }
    _showToast('Disconnected VocalPoint device');
  }

  Future<void> _selectOutputDevice(BleDevice device) async {
    final name = _deviceLabel(device, fallback: 'Output device');

    setState(() => _pendingOutputId = device.deviceId);

    try {
      if (_isScanning) {
        await _stopScan();
      }

      await Future<void>.delayed(const Duration(milliseconds: 750));
      AppState.bleAddress.value = device.deviceId;
      AppState.audioOutputDeviceName.value = name;
      AppState.param1.value = name;

      await _syncSelectedOutputToDevice(showSuccess: false);
      if (!mounted) {
        return;
      }
      setState(() {
        _pendingOutputId = null;
        _expandedPanel = null;
      });
      _handleSetupStateChanged();
      _showToast('Selected output device: $name');
    } finally {
      if (mounted) {
        setState(() => _pendingOutputId = null);
      }
    }
  }

  Future<void> _clearOutputSelection() async {
    AppState.clearOutputSelection();
    _showToast('Cleared output device selection');
  }

  Future<void> _selectOutputDeviceName(String name) async {
    final trimmedName = name.trim();
    if (trimmedName.isEmpty) {
      return;
    }

    AppState.audioOutputDeviceName.value = trimmedName;
    AppState.param1.value = trimmedName;
    await _syncSelectedOutputToDevice(showSuccess: false);
    if (!mounted) {
      return;
    }
    setState(() {
      _pendingOutputId = null;
      _expandedPanel = null;
    });
    _handleSetupStateChanged();
    _showToast('Selected output device: $trimmedName');
  }

  Future<void> _writeCharacteristic({
    required String charUuid,
    required Uint8List payload,
    bool showSuccess = false,
    bool showErrors = true,
    String? successMessage,
  }) async {
    final deviceId = AppState.connectedDeviceId.value;
    if (deviceId == null) {
      if (showErrors) {
        _showToast('No VocalPoint device connected');
      }
      return;
    }

    final serviceUuid = AppState.volumeServiceUuid.value.trim();
    if (serviceUuid.isEmpty || charUuid.trim().isEmpty) {
      if (showErrors) {
        _showToast('Service/characteristic UUID is missing');
      }
      return;
    }

    try {
      await UniversalBle.writeValue(
        deviceId,
        serviceUuid,
        charUuid.trim(),
        payload,
        BleOutputProperty.withResponse,
      );
      if (showSuccess && successMessage != null) {
        _showToast(successMessage);
      }
    } catch (error) {
      if (showErrors) {
        _showToast('Write failed: $error');
      }
    }
  }

  Future<void> _writeMetadataToken(
    String token, {
    bool showSuccess = false,
    String? successMessage,
  }) async {
    await _writeCharacteristic(
      charUuid: AppState.metadataCharUuid.value,
      payload: Uint8List.fromList(utf8.encode(token)),
      showSuccess: showSuccess,
      showErrors: showSuccess,
      successMessage: successMessage ?? 'Sent $token',
    );
  }

  Future<void> _writeVolumeToDevice({bool showSuccess = false}) async {
    final volume = AppState.isMuted.value
        ? 0
        : AppState.volume.value.round().clamp(0, 100);
    await _writeCharacteristic(
      charUuid: AppState.volumeCharUuid.value,
      payload: Uint8List.fromList(<int>[volume]),
      showSuccess: showSuccess,
      showErrors: showSuccess,
      successMessage: 'Sent volume=$volume',
    );
  }

  Future<void> _syncSelectedOutputToDevice({bool showSuccess = true}) async {
    final outputName = AppState.audioOutputDeviceName.value?.trim() ?? '';

    if (outputName.isEmpty) {
      if (showSuccess) {
        _showToast('Select an output device first');
      }
      return;
    }

    if (AppState.usePhoneScannedOutputDevices) {
      final address = AppState.bleAddress.value.trim();
      if (address.isEmpty) {
        if (showSuccess) {
          _showToast('Select an output device first');
        }
        return;
      }
      await _writeMetadataToken('BLE_UUID_ADDR=$address', showSuccess: false);
    }

    await _writeMetadataToken('AUDIO_OUT_NAME=$outputName', showSuccess: false);

    if (showSuccess) {
      _showToast(
        AppState.usePhoneScannedOutputDevices
            ? 'Sent BLE_UUID_ADDR and AUDIO_OUT_NAME'
            : 'Sent AUDIO_OUT_NAME',
      );
    }
  }

  Future<void> _sendVoiceProfileSelection(
    int voiceProfileNum, {
    bool showSuccess = true,
  }) async {
    AppState.voiceProfileNum.value = voiceProfileNum;
    await _writeMetadataToken(
      'VOICE_PROFILE_NUM=$voiceProfileNum',
      showSuccess: showSuccess,
      successMessage: 'Sent VOICE_PROFILE_NUM=$voiceProfileNum',
    );
  }

  Future<void> _requestRemoteReboot() async {
    await _writeMetadataToken(
      'REBOOT=1',
      showSuccess: true,
      successMessage: 'Sent REBOOT=1',
    );
  }

  void _rememberVoiceProfile(String name, int number) {
    final trimmedName = name.trim();
    if (trimmedName.isEmpty) {
      return;
    }

    final current = List<VoiceProfileChoice>.from(AppState.voiceProfiles.value);
    final index = current.indexWhere(
      (entry) => entry.number == number || entry.name == trimmedName,
    );

    final next = VoiceProfileChoice(number: number, name: trimmedName);
    if (index == -1) {
      current.add(next);
    } else {
      current[index] = next;
    }

    current.sort((lhs, rhs) => lhs.number.compareTo(rhs.number));
    AppState.voiceProfiles.value = current;
  }

  void _rememberOutputDeviceName(String name) {
    final trimmedName = name.trim();
    if (trimmedName.isEmpty) {
      return;
    }

    final current = List<String>.from(AppState.outputDeviceOptions.value);
    if (current.contains(trimmedName)) {
      return;
    }

    current.add(trimmedName);
    current.sort();
    AppState.outputDeviceOptions.value = current;
  }

  void _applyMetadataPayload(String payload) {
    final values = <String, String>{};

    for (final token in payload.split(';')) {
      final trimmedToken = token.trim();
      if (trimmedToken.isEmpty) {
        continue;
      }

      final separator = trimmedToken.indexOf('=');
      if (separator <= 0) {
        continue;
      }

      values[trimmedToken.substring(0, separator).trim().toUpperCase()] =
          trimmedToken.substring(separator + 1).trim();
    }

    if (values.containsKey('BLE_UUID_ADDR')) {
      AppState.bleAddress.value = values['BLE_UUID_ADDR']!;
    } else if (values.containsKey('BLE_ADDR')) {
      AppState.bleAddress.value = values['BLE_ADDR']!;
    }

    final announcedOutputName = values['AUDIO_OUT_NAME_SEND'];
    if (announcedOutputName != null) {
      _rememberOutputDeviceName(announcedOutputName);
    }

    final selectedOutputName =
        values['AUDIO_OUT_NAME_SET'] ??
        values['AUDIO_OUT_NAME'];
    if (selectedOutputName != null) {
      AppState.audioOutputDeviceName.value = selectedOutputName;
      AppState.param1.value = selectedOutputName;
    } else if (values.containsKey('PARAM1')) {
      AppState.param1.value = values['PARAM1']!;
    }

    if (values.containsKey('VOICE_PROFILE_NUM')) {
      final parsed = int.tryParse(values['VOICE_PROFILE_NUM']!);
      if (parsed != null) {
        AppState.voiceProfileNum.value = parsed;
      }
    }

    final voiceName =
        values['VOICE_PROFILE_NAME'] ??
        values['VOICE_PROFILE'] ??
        values['VOICE'];
    final voiceNameNum = values['VOICE_PROFILE_NAME_NUM'];
    if (voiceName != null && voiceNameNum != null) {
      final parsed = int.tryParse(voiceNameNum);
      if (parsed != null) {
        _rememberVoiceProfile(voiceName, parsed);
      }
    }
  }

  Future<void> _refreshMetadataFromDevice({bool showErrors = false}) async {
    final deviceId = AppState.connectedDeviceId.value;
    if (deviceId == null) {
      return;
    }

    try {
      final payload = await UniversalBle.readValue(
        deviceId,
        AppState.volumeServiceUuid.value,
        AppState.metadataCharUuid.value,
      );
      _applyMetadataPayload(utf8.decode(payload, allowMalformed: true));
    } catch (error) {
      if (showErrors) {
        _showToast('Metadata read failed: $error');
      }
    }
  }

  void _startMetadataRefresh() {
    _stopMetadataRefresh();
    _metadataRefreshTimer = Timer.periodic(
      const Duration(milliseconds: 300),
      (_) => _refreshMetadataFromDevice(showErrors: false),
    );
  }

  void _stopMetadataRefresh() {
    _metadataRefreshTimer?.cancel();
    _metadataRefreshTimer = null;
  }

  void _onVolumeChanged(double value) {
    AppState.volume.value = value;
    if (!AppState.isMuted.value) {
      _lastNonMutedVolume = value;
    }

    _volumeWriteDebounce?.cancel();
    _volumeWriteDebounce = Timer(
      const Duration(milliseconds: 140),
      () => _writeVolumeToDevice(),
    );
  }

  Future<void> _toggleMute(bool muted) async {
    if (!muted) {
      AppState.isMuted.value = false;
      if (AppState.volume.value == 0) {
        AppState.volume.value = _lastNonMutedVolume.clamp(0, 100);
      }
      await _writeVolumeToDevice(showSuccess: true);
      return;
    }

    _lastNonMutedVolume = AppState.volume.value;
    AppState.isMuted.value = true;
    await _writeVolumeToDevice(showSuccess: true);
  }

  Future<void> _showServicesForConnected() async {
    final deviceId = AppState.connectedDeviceId.value;
    if (deviceId == null) {
      _showToast('No VocalPoint device connected');
      return;
    }

    try {
      final services = await UniversalBle.discoverServices(deviceId);
      if (!mounted) return;
      showDialog<void>(
        context: context,
        builder: (context) {
          return AlertDialog(
            backgroundColor: AppColors.panelSoft,
            title: const Text('Discovered services'),
            content: SingleChildScrollView(
              child: Text(
                services.toString(),
                style: const TextStyle(color: AppColors.white),
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Close'),
              ),
            ],
          );
        },
      );
    } catch (error) {
      _showToast('Discover services failed: $error');
    }
  }

  void _handleProfileMenu(ProfileMenuAction action) {
    switch (action) {
      case ProfileMenuAction.about:
        _showAboutDialog();
      case ProfileMenuAction.systemMetadata:
        _showSystemMetadataDialog();
      case ProfileMenuAction.deviceDiagnostics:
        _showDeviceDiagnosticsDialog();
    }
  }

  void _showAboutDialog() {
    _showOverlayDialog(
      title: 'About',
      childBuilder: (dialogContext) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: AspectRatio(
              aspectRatio: 4 / 3,
              child: Image.asset('assets/Good_Pic_Two.jpg', fit: BoxFit.cover),
            ),
          ),
          const SizedBox(height: 18),
          const Text(
            'VocalPoint',
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 8),
          const Text('Version 1.0.0', style: TextStyle(color: AppColors.muted)),
          const SizedBox(height: 16),
          const Text(
            'A portable device that connects to hearing aids (and headphones), denoising conversations in realtime.',
            style: TextStyle(color: AppColors.white, height: 1.5),
          ),
        ],
      ),
    );
  }

  void _showSystemMetadataDialog() {
    _showOverlayDialog(
      title: 'System and Metadata',
      childBuilder: (dialogContext) => _buildSystemMetadataContent(),
    );
  }

  void _showDeviceDiagnosticsDialog() {
    _showOverlayDialog(
      title: 'Device Diagnostics',
      childBuilder: (dialogContext) => _buildDeviceDiagnosticsContent(),
    );
  }

  void _showOverlayDialog({
    required String title,
    required WidgetBuilder childBuilder,
  }) {
    showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return Dialog(
          backgroundColor: Colors.transparent,
          insetPadding: const EdgeInsets.symmetric(
            horizontal: 20,
            vertical: 24,
          ),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 640),
            child: Container(
              decoration: BoxDecoration(
                color: AppColors.panelSoft,
                borderRadius: BorderRadius.circular(28),
                border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.35),
                    blurRadius: 30,
                    offset: const Offset(0, 18),
                  ),
                ],
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(22, 18, 12, 8),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            title,
                            style: const TextStyle(
                              fontSize: 22,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ),
                        IconButton(
                          onPressed: () => Navigator.of(dialogContext).pop(),
                          icon: const Icon(Icons.close),
                          tooltip: 'Close',
                        ),
                      ],
                    ),
                  ),
                  Flexible(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.fromLTRB(22, 8, 22, 22),
                      child: childBuilder(dialogContext),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          Positioned.fill(child: SignalBackground(accent: _highlightColor)),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.black.withValues(alpha: 0.18),
                    Colors.black.withValues(alpha: 0.58),
                    Colors.black.withValues(alpha: 0.82),
                  ],
                ),
              ),
            ),
          ),
          SafeArea(child: _buildSetupView(context)),
          if (_showSplashOverlay) _buildSplashOverlay(),
        ],
      ),
    );
  }

  Widget _buildSplashOverlay() {
    return Positioned.fill(
      child: IgnorePointer(
        child: AnimatedOpacity(
          opacity: _fadeSplashOverlay ? 0 : 1,
          duration: const Duration(milliseconds: 240),
          curve: Curves.easeOutCubic,
          child: Container(
            color: Colors.black,
            alignment: Alignment.center,
            child: SvgPicture.asset(
              'assets/Squiggly-cropped.svg',
              width: 84,
              height: 84,
              colorFilter: const ColorFilter.mode(
                AppColors.white,
                BlendMode.srcIn,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSetupView(BuildContext context) {
    return LayoutBuilder(
      key: const ValueKey<String>('setup-view'),
      builder: (context, constraints) {
        final maxWidth = math.min(constraints.maxWidth - 32, 680.0);
        return Align(
          alignment: Alignment.topCenter,
          child: Stack(
            children: [
              SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(14, 16, 14, 40),
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: maxWidth),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _buildTopBar(),
                      const SizedBox(height: 88),
                      Padding(
                        padding: const EdgeInsets.fromLTRB(6, 0, 6, 20),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            LayoutBuilder(
                              builder: (context, constraints) {
                                final showSideBySide =
                                    constraints.maxWidth >= 620;

                                if (!showSideBySide) {
                                  return Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.stretch,
                                    children: [
                                      _buildConnectionPanel(
                                        SetupPanel.vocalPoint,
                                      ),
                                      const SizedBox(height: 34),
                                      _buildConnectionPanel(SetupPanel.output),
                                    ],
                                  );
                                }

                                return Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Expanded(
                                      child: _buildConnectionPanel(
                                        SetupPanel.vocalPoint,
                                      ),
                                    ),
                                    const SizedBox(width: 22),
                                    Expanded(
                                      child: _buildConnectionPanel(
                                        SetupPanel.output,
                                      ),
                                    ),
                                  ],
                                );
                              },
                            ),
                            const SizedBox(height: 12),
                            Align(
                              alignment: Alignment.center,
                              child: TextButton(
                                onPressed: _skipToDashboard,
                                style: TextButton.styleFrom(
                                  foregroundColor: AppColors.white.withValues(
                                    alpha: 0.65,
                                  ),
                                  textStyle: const TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.w600,
                                    letterSpacing: 0.3,
                                  ),
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 12,
                                    vertical: 8,
                                  ),
                                ),
                                child: Text(
                                  _dashboardUnlocked ? 'Close' : 'Skip',
                                ),
                              ),
                            ),
                            if (_dashboardUnlocked) ...[
                              const SizedBox(height: 18),
                              Align(
                                alignment: Alignment.center,
                                child: Wrap(
                                  alignment: WrapAlignment.center,
                                  spacing: 10,
                                  runSpacing: 10,
                                  children: [
                                    _StatusChip(
                                      label: _hasConnectedVocalPoint
                                          ? 'VocalPoint linked'
                                          : 'VocalPoint offline',
                                      color: _hasConnectedVocalPoint
                                          ? AppColors.success
                                          : AppColors.danger,
                                      icon: _hasConnectedVocalPoint
                                          ? Icons.check_circle
                                          : Icons.bluetooth_disabled,
                                    ),
                                    _StatusChip(
                                      label: _hasSelectedOutputDevice
                                          ? 'Output selected'
                                          : 'Output missing',
                                      color: _hasSelectedOutputDevice
                                          ? AppColors.success
                                          : AppColors.danger,
                                      icon: _hasSelectedOutputDevice
                                          ? Icons.headphones
                                          : Icons.portable_wifi_off,
                                    ),
                                  ],
                                ),
                              ),
                              const SizedBox(height: 52),
                              LayoutBuilder(
                                builder: (context, constraints) {
                                  final wide = constraints.maxWidth >= 620;
                                  if (!wide) {
                                    return Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.stretch,
                                      children: [
                                        _buildVolumeCard(context),
                                        const SizedBox(height: 34),
                                        _buildVoiceMixCard(context),
                                      ],
                                    );
                                  }

                                  return Row(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Expanded(
                                        child: _buildVolumeCard(context),
                                      ),
                                      const SizedBox(width: 22),
                                      Expanded(
                                        child: _buildVoiceMixCard(context),
                                      ),
                                    ],
                                  );
                                },
                              ),
                            ],
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildTopBar() {
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < 390;
        final menuSize = compact ? 48.0 : 56.0;
        final menuPadding = compact ? 10.0 : 12.0;

        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Spacer(),
            PopupMenuButton<ProfileMenuAction>(
              onSelected: _handleProfileMenu,
              color: AppColors.panelSoft.withValues(alpha: 0.97),
              itemBuilder: (context) => const [
                PopupMenuItem(
                  value: ProfileMenuAction.about,
                  child: Text('About'),
                ),
                PopupMenuItem(
                  value: ProfileMenuAction.systemMetadata,
                  child: Text('System and metadata'),
                ),
                PopupMenuItem(
                  value: ProfileMenuAction.deviceDiagnostics,
                  child: Text('Device diagnostics'),
                ),
              ],
              child: Container(
                width: menuSize,
                height: menuSize,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.white.withValues(alpha: 0.06),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.12),
                  ),
                ),
                padding: EdgeInsets.all(menuPadding),
                child: SvgPicture.asset(
                  'assets/Squiggly-cropped.svg',
                  colorFilter: const ColorFilter.mode(
                    AppColors.white,
                    BlendMode.srcIn,
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildConnectionPanel(SetupPanel panel) {
    final accent = _highlightColor;
    final compact = MediaQuery.sizeOf(context).width < 390;
    final circleSize = compact ? 92.0 : 114.0;
    final loaderSize = compact ? 76.0 : 94.0;
    final iconSize = compact ? 44.0 : 58.0;
    final labelFontSize = compact ? 11.5 : 13.0;
    final actionFontSize = compact ? 14.0 : 15.5;
    final isVocalPoint = panel == SetupPanel.vocalPoint;
    final isExpanded = _expandedPanel == panel;
    final isScanning = _isScanning && _activeScanTarget == panel;
    final canScan = isVocalPoint || AppState.usePhoneScannedOutputDevices;
    final isConnected = isVocalPoint
        ? _hasConnectedVocalPoint
        : _hasSelectedOutputDevice;
    final isConnecting = isVocalPoint
        ? _pendingVocalPointId != null
        : _pendingOutputId != null;
    final title = isVocalPoint ? 'VocalPoint' : 'Output Device';
    final connectionLabel = isConnected
        ? (isVocalPoint
              ? (AppState.connectedDeviceName.value ?? 'Connected')
              : (AppState.audioOutputDeviceName.value ?? 'Selected'))
        : title;
    final actionLabel = isScanning
        ? 'Scanning...'
        : (isVocalPoint
              ? 'Scan for VocalPoint devices'
              : (AppState.usePhoneScannedOutputDevices
                    ? 'Scan for output devices'
                    : 'Output device names are announced by the RPi over BLE metadata.'));
    final results = isVocalPoint ? _vocalPointResults : _outputResults;

    return AnimatedSize(
      duration: _panelAnimationDuration,
      curve: Curves.easeInOutCubicEmphasized,
      child: AnimatedContainer(
        duration: _panelAnimationDuration,
        curve: Curves.easeInOutCubicEmphasized,
        padding: isExpanded
            ? EdgeInsets.fromLTRB(
                compact ? 10 : 14,
                compact ? 12 : 16,
                compact ? 10 : 14,
                compact ? 10 : 14,
              )
            : EdgeInsets.zero,
        decoration: isExpanded
            ? BoxDecoration(
                borderRadius: BorderRadius.circular(30),
                color: Colors.white.withValues(alpha: 0.06),
                border: Border.all(
                  color: isConnected
                      ? AppColors.success.withValues(alpha: 0.45)
                      : accent.withValues(alpha: 0.42),
                  width: 1.3,
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.16),
                    blurRadius: 20,
                    offset: const Offset(0, 10),
                  ),
                ],
              )
            : null,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Column(
                children: [
                  GestureDetector(
                    onTap: () => _openPanel(panel),
                    child: AnimatedContainer(
                      duration: _panelIconAnimationDuration,
                      curve: Curves.easeInOutCubicEmphasized,
                      width: circleSize,
                      height: circleSize,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: isConnected
                            ? const Color(0xFF13905A)
                            : (isExpanded || isScanning
                                  ? shiftLightness(accent, -0.22)
                                  : shiftLightness(accent, -0.30)),
                        border: Border.all(
                          color: isConnected
                              ? AppColors.success.withValues(alpha: 0.9)
                              : _highlightBright.withValues(alpha: 0.78),
                          width: isExpanded || isScanning ? 1.8 : 1.4,
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: (isConnected ? AppColors.success : accent)
                                .withValues(alpha: 0.20),
                            blurRadius: 18,
                            offset: const Offset(0, 10),
                          ),
                        ],
                      ),
                      child: Stack(
                        alignment: Alignment.center,
                        children: [
                          if (isConnecting || isScanning)
                            SizedBox(
                              width: loaderSize,
                              height: loaderSize,
                              child: CircularProgressIndicator(
                                strokeWidth: compact ? 2.2 : 2.6,
                                valueColor: AlwaysStoppedAnimation<Color>(
                                  isConnected ? AppColors.white : accent,
                                ),
                              ),
                            ),
                          Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                isVocalPoint
                                    ? Icons.graphic_eq
                                    : Icons.headphones,
                                size: iconSize,
                                color: AppColors.white,
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                  SizedBox(height: compact ? 8 : 12),
                  Text(
                    connectionLabel,
                    textAlign: TextAlign.center,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: labelFontSize,
                      fontWeight: FontWeight.w700,
                      height: 1.15,
                    ),
                  ),
                ],
              ),
            ),
            if (isExpanded) ...[
              SizedBox(height: compact ? 10 : 14),
              GlassCard(
                padding: EdgeInsets.fromLTRB(
                  compact ? 14 : 18,
                  compact ? 14 : 18,
                  compact ? 14 : 18,
                  compact ? 14 : 18,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      alignment: WrapAlignment.spaceBetween,
                      children: [
                        ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 340),
                          child: Text(
                            actionLabel,
                            style: Theme.of(context).textTheme.titleMedium
                                ?.copyWith(
                                  fontWeight: FontWeight.w700,
                                  fontSize: actionFontSize,
                                  height: 1.2,
                                ),
                          ),
                        ),
                        Wrap(
                          spacing: 10,
                          runSpacing: 10,
                          children: [
                            if (canScan)
                              FilledButton.icon(
                                onPressed: isScanning
                                    ? null
                                    : () => _startScan(panel),
                                style: FilledButton.styleFrom(
                                  backgroundColor: accent,
                                  foregroundColor: Colors.black,
                                ),
                                icon: isScanning
                                    ? const SizedBox(
                                        width: 16,
                                        height: 16,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                          color: Colors.black,
                                        ),
                                      )
                                    : const Icon(Icons.radar),
                                label: Text(isScanning ? 'Scanning...' : 'Scan'),
                              ),
                            if (canScan && isScanning)
                              OutlinedButton.icon(
                                onPressed: _stopScan,
                                icon: const Icon(Icons.pause_circle_outline),
                                label: const Text('Stop'),
                              ),
                          ],
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),
                    _buildSelectedSummary(panel),
                    const SizedBox(height: 16),
                    if (!isVocalPoint && !AppState.usePhoneScannedOutputDevices)
                      _buildOutputOptionsList()
                    else if (results.isEmpty)
                      Container(
                        padding: const EdgeInsets.all(18),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(20),
                          color: Colors.white.withValues(alpha: 0.04),
                          border: Border.all(
                            color: Colors.white.withValues(alpha: 0.08),
                          ),
                        ),
                        child: Text(
                          isScanning
                              ? 'Scanning for nearby devices...'
                              : 'No devices yet. Start a scan to populate this list.',
                          style: const TextStyle(color: AppColors.muted),
                        ),
                      )
                    else
                      ...results.map(
                        (device) => _buildScanResultTile(panel, device),
                      ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildSelectedSummary(SetupPanel panel) {
    final accent = _highlightColor;
    final accentBright = _highlightBright;
    final isVocalPoint = panel == SetupPanel.vocalPoint;
    final selectedName = isVocalPoint
        ? AppState.connectedDeviceName.value
        : AppState.audioOutputDeviceName.value;
    final isReady = isVocalPoint
        ? _hasConnectedVocalPoint
        : _hasSelectedOutputDevice;

    return LayoutBuilder(
      builder: (context, constraints) {
        final showActionsBelow = constraints.maxWidth < 430;
        final actions = Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            if (isVocalPoint && isReady)
              TextButton(
                onPressed: _showServicesForConnected,
                child: const Text('Services'),
              ),
            if (isReady)
              TextButton(
                onPressed: isVocalPoint
                    ? _disconnectVocalPoint
                    : _clearOutputSelection,
                child: Text(isVocalPoint ? 'Disconnect' : 'Clear'),
              ),
          ],
        );

        return Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            color: Colors.white.withValues(alpha: 0.06),
            border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 42,
                    height: 42,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: (isReady ? AppColors.success : accent).withValues(
                        alpha: 0.18,
                      ),
                    ),
                    child: Icon(
                      isVocalPoint
                          ? Icons.bluetooth_connected
                          : Icons.surround_sound,
                      color: isReady ? AppColors.success : accentBright,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          isReady
                              ? (selectedName ?? 'Connected device')
                              : 'No device selected',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 16,
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (!showActionsBelow) ...[
                    const SizedBox(width: 12),
                    Flexible(child: actions),
                  ],
                ],
              ),
              if (showActionsBelow && isReady) ...[
                const SizedBox(height: 12),
                actions,
              ],
            ],
          ),
        );
      },
    );
  }

  Widget _buildScanResultTile(SetupPanel panel, BleDevice device) {
    final accent = _highlightColor;
    final accentBright = _highlightBright;
    final isVocalPoint = panel == SetupPanel.vocalPoint;
    final name = device.name?.trim().isNotEmpty == true
        ? device.name!.trim()
        : device.deviceId;
    final isCurrent = isVocalPoint
        ? AppState.connectedDeviceId.value == device.deviceId
        : AppState.bleAddress.value == device.deviceId;
    final isPending = isVocalPoint
        ? _pendingVocalPointId == device.deviceId
        : _pendingOutputId == device.deviceId;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: Colors.white.withValues(alpha: 0.05),
        border: Border.all(
          color: isCurrent
              ? AppColors.success.withValues(alpha: 0.55)
              : Colors.white.withValues(alpha: 0.08),
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: (isCurrent ? AppColors.success : accent).withValues(
                alpha: 0.16,
              ),
            ),
            child: Icon(
              isVocalPoint ? Icons.memory : Icons.headset,
              color: isCurrent ? AppColors.success : accentBright,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 15,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          FilledButton(
            onPressed: isCurrent
                ? null
                : (isPending
                      ? null
                      : () => isVocalPoint
                            ? _connectToVocalPoint(device)
                            : _selectOutputDevice(device)),
            style: FilledButton.styleFrom(
              backgroundColor: isCurrent ? AppColors.success : accent,
              foregroundColor: isCurrent ? Colors.white : Colors.black,
            ),
            child: isPending
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.black,
                    ),
                  )
                : Text(
                    isCurrent ? 'Ready' : (isVocalPoint ? 'Connect' : 'Use'),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildOutputOptionsList() {
    final accent = _highlightColor;
    final accentBright = _highlightBright;

    return ValueListenableBuilder<List<String>>(
      valueListenable: AppState.outputDeviceOptions,
      builder: (context, options, _) {
        if (options.isEmpty) {
          return Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(20),
              color: Colors.white.withValues(alpha: 0.04),
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.08),
              ),
            ),
            child: const Text(
              'Waiting for output device names from the ESP32/RPi bridge.',
              style: TextStyle(color: AppColors.muted),
            ),
          );
        }

        return ValueListenableBuilder<String?>(
          valueListenable: AppState.audioOutputDeviceName,
          builder: (context, selectedName, _) {
            final selected = selectedName?.trim() ?? '';
            return Column(
              children: options.map((name) {
                final isCurrent = selected == name;
                return Container(
                  margin: const EdgeInsets.only(bottom: 10),
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(20),
                    color: Colors.white.withValues(alpha: 0.05),
                    border: Border.all(
                      color: isCurrent
                          ? AppColors.success.withValues(alpha: 0.55)
                          : Colors.white.withValues(alpha: 0.08),
                    ),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: (isCurrent ? AppColors.success : accent)
                              .withValues(alpha: 0.16),
                        ),
                        child: Icon(
                          Icons.headset,
                          color: isCurrent ? AppColors.success : accentBright,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          name,
                          style: const TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 15,
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      FilledButton(
                        onPressed: isCurrent
                            ? null
                            : () => _selectOutputDeviceName(name),
                        style: FilledButton.styleFrom(
                          backgroundColor: isCurrent
                              ? AppColors.success
                              : accent,
                          foregroundColor: isCurrent
                              ? Colors.white
                              : Colors.black,
                        ),
                        child: Text(isCurrent ? 'Selected' : 'Choose'),
                      ),
                    ],
                  ),
                );
              }).toList(),
            );
          },
        );
      },
    );
  }

  Widget _buildVolumeCard(BuildContext context) {
    final accent = _highlightColor;
    final accentBright = _highlightBright;
    return _buildControlPanelShell(
      panel: ControlPanel.volume,
      title: 'Control',
      icon: Icons.volume_up_rounded,
      child: GlassCard(
        padding: const EdgeInsets.all(22),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _CardHeading(
              eyebrow: 'Control',
              title: 'Volume and mute',
              subtitle:
                  'Write direct volume values to the ESP32 volume characteristic.',
              accent: accentBright,
            ),
            const SizedBox(height: 34),
            ValueListenableBuilder<bool>(
              valueListenable: AppState.isMuted,
              builder: (context, muted, _) {
                return ValueListenableBuilder<double>(
                  valueListenable: AppState.volume,
                  builder: (context, volume, __) {
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _MetricChip(
                          label: muted ? 'Muted' : 'Live',
                          icon: muted ? Icons.volume_off : Icons.volume_up,
                          accent: muted ? AppColors.danger : AppColors.success,
                        ),
                        const SizedBox(height: 18),
                        Center(
                          child: Column(
                            children: [
                              Text(
                                '${volume.round()}',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  fontSize: 36,
                                  fontWeight: FontWeight.w800,
                                  color: accentBright,
                                  height: 1,
                                ),
                              ),
                              const SizedBox(height: 4),
                              const Text(
                                'Volume',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  color: AppColors.mutedSoft,
                                  fontWeight: FontWeight.w600,
                                  letterSpacing: 0.4,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 16),
                        SliderTheme(
                          data: SliderTheme.of(context).copyWith(
                            activeTrackColor: accent,
                            inactiveTrackColor: Colors.white.withValues(
                              alpha: 0.12,
                            ),
                            thumbColor: accentBright,
                            overlayColor: accent.withValues(alpha: 0.16),
                            trackHeight: 5,
                          ),
                          child: Slider(
                            value: volume,
                            min: 0,
                            max: 100,
                            divisions: 100,
                            onChanged: muted ? null : _onVolumeChanged,
                          ),
                        ),
                        const SizedBox(height: 10),
                        Row(
                          children: [
                            Expanded(
                              child: Container(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 16,
                                  vertical: 14,
                                ),
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(18),
                                  color: Colors.white.withValues(alpha: 0.05),
                                ),
                                child: Row(
                                  children: [
                                    const Icon(
                                      Icons.volume_mute_outlined,
                                      color: AppColors.muted,
                                    ),
                                    const SizedBox(width: 12),
                                    const Expanded(
                                      child: Text(
                                        'Full mute',
                                        style: TextStyle(
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                    ),
                                    Switch.adaptive(
                                      value: muted,
                                      activeThumbColor: AppColors.success,
                                      activeTrackColor: AppColors.success
                                          .withValues(alpha: 0.35),
                                      onChanged: _toggleMute,
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        FilledButton.icon(
                          onPressed: () =>
                              _writeVolumeToDevice(showSuccess: true),
                          style: FilledButton.styleFrom(
                            backgroundColor: accent,
                            foregroundColor: Colors.black,
                          ),
                          icon: const Icon(Icons.send),
                          label: const Text('Send volume now'),
                        ),
                      ],
                    );
                  },
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildVoiceMixCard(BuildContext context) {
    final accent = _highlightColor;
    final accentBright = _highlightBright;
    return _buildControlPanelShell(
      panel: ControlPanel.mix,
      title: 'Mix',
      icon: Icons.multitrack_audio_rounded,
      child: GlassCard(
        padding: const EdgeInsets.all(22),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _CardHeading(
              eyebrow: 'Mix',
              title: 'Voice balance',
              subtitle:
                  'Voice options are populated from BLE metadata fed by the ESP32.',
              accent: accentBright,
            ),
            const SizedBox(height: 34),
            ValueListenableBuilder<List<VoiceProfileChoice>>(
              valueListenable: AppState.voiceProfiles,
              builder: (context, options, _) {
                if (options.isEmpty) {
                  return Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(18),
                      color: Colors.white.withValues(alpha: 0.05),
                      border: Border.all(
                        color: Colors.white.withValues(alpha: 0.08),
                      ),
                    ),
                    child: const Text(
                      'Waiting for voice profiles from the ESP32/RPi bridge.',
                      style: TextStyle(color: AppColors.muted),
                    ),
                  );
                }

                return Column(
                  children: [
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxHeight: 320),
                      child: SingleChildScrollView(
                        child: Column(
                          children: options
                              .map(
                                (option) => Padding(
                                  padding: const EdgeInsets.only(bottom: 12),
                                  child: InkWell(
                                    onTap: () =>
                                        _sendVoiceProfileSelection(option.number),
                                    borderRadius: BorderRadius.circular(18),
                                    child: ValueListenableBuilder<int>(
                                      valueListenable: AppState.voiceProfileNum,
                                      builder: (context, selected, _) {
                                        final active = selected == option.number;
                                        return AnimatedContainer(
                                          duration: const Duration(milliseconds: 220),
                                          padding: const EdgeInsets.all(16),
                                          decoration: BoxDecoration(
                                            borderRadius: BorderRadius.circular(18),
                                            color: active
                                                ? accent.withValues(alpha: 0.18)
                                                : Colors.white.withValues(alpha: 0.05),
                                            border: Border.all(
                                              color: active
                                                  ? accent.withValues(alpha: 0.72)
                                                  : Colors.white.withValues(
                                                      alpha: 0.08,
                                                    ),
                                            ),
                                          ),
                                          child: Row(
                                            children: [
                                              Icon(
                                                active
                                                    ? Icons.multitrack_audio
                                                    : Icons.person_2_outlined,
                                                color: active
                                                    ? accentBright
                                                    : AppColors.muted,
                                              ),
                                              const SizedBox(width: 22),
                                              Expanded(
                                                child: Text(
                                                  option.name,
                                                  style: const TextStyle(
                                                    fontWeight: FontWeight.w600,
                                                  ),
                                                ),
                                              ),
                                              if (active)
                                                Icon(
                                                  Icons.check_circle,
                                                  color: accentBright,
                                                ),
                                            ],
                                          ),
                                        );
                                      },
                                    ),
                                  ),
                                ),
                              )
                              .toList(),
                        ),
                      ),
                    ),
                  ],
                );
              },
            ),
            const SizedBox(height: 8),
            const Text(
              'Each new VOICE token discovered over BLE is added here as a selectable Mix target.',
              style: TextStyle(color: AppColors.muted),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildControlPanelShell({
    required ControlPanel panel,
    required String title,
    required IconData icon,
    required Widget child,
  }) {
    final accent = _highlightColor;
    final compact = MediaQuery.sizeOf(context).width < 390;
    final circleSize = compact ? 92.0 : 114.0;
    final iconSize = compact ? 44.0 : 58.0;
    final isExpanded = _expandedControlPanel == panel;

    return AnimatedSize(
      duration: _panelAnimationDuration,
      curve: Curves.easeInOutCubicEmphasized,
      child: AnimatedContainer(
        duration: _panelAnimationDuration,
        curve: Curves.easeInOutCubicEmphasized,
        padding: isExpanded
            ? EdgeInsets.fromLTRB(
                compact ? 10 : 14,
                compact ? 12 : 16,
                compact ? 10 : 14,
                compact ? 10 : 14,
              )
            : EdgeInsets.zero,
        decoration: isExpanded
            ? BoxDecoration(
                borderRadius: BorderRadius.circular(30),
                color: Colors.white.withValues(alpha: 0.06),
                border: Border.all(
                  color: accent.withValues(alpha: 0.42),
                  width: 1.3,
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.16),
                    blurRadius: 20,
                    offset: const Offset(0, 10),
                  ),
                ],
              )
            : null,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Column(
                children: [
                  GestureDetector(
                    onTap: () => _toggleControlPanel(panel),
                    child: AnimatedContainer(
                      duration: _panelIconAnimationDuration,
                      curve: Curves.easeInOutCubicEmphasized,
                      width: circleSize,
                      height: circleSize,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: isExpanded
                            ? shiftLightness(accent, -0.22)
                            : shiftLightness(accent, -0.30),
                        border: Border.all(
                          color: _highlightBright.withValues(alpha: 0.78),
                          width: isExpanded ? 1.8 : 1.4,
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: accent.withValues(alpha: 0.20),
                            blurRadius: 18,
                            offset: const Offset(0, 10),
                          ),
                        ],
                      ),
                      child: Icon(icon, size: iconSize, color: AppColors.white),
                    ),
                  ),
                  SizedBox(height: compact ? 8 : 12),
                  Text(
                    title,
                    textAlign: TextAlign.center,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: compact ? 13 : 15,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
            if (isExpanded) ...[SizedBox(height: compact ? 10 : 14), child],
          ],
        ),
      ),
    );
  }

  Widget _buildDeviceDiagnosticsContent() {
    final accentBright = _highlightBright;
    final diagnostics = <_DiagnosticMetric>[
      _DiagnosticMetric(
        label: 'BLE address',
        value: AppState.bleAddress.value.isEmpty
            ? 'Not selected'
            : AppState.bleAddress.value,
      ),
      _DiagnosticMetric(
        label: 'Output name',
        value: AppState.audioOutputDeviceName.value ?? 'Not selected',
      ),
      _DiagnosticMetric(label: 'ESP32 temp', value: '41.8 C'),
      _DiagnosticMetric(label: 'CPU load', value: '18%'),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        const Text(
          'Transport state for the current setup.',
          style: TextStyle(color: AppColors.muted, height: 1.5),
        ),
        const SizedBox(height: 18),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: diagnostics
              .map(
                (metric) => _MetricChip(
                  label: '${metric.label}: ${metric.value}',
                  icon: Icons.circle,
                  accent: accentBright,
                ),
              )
              .toList(),
        ),
      ],
    );
  }

  Widget _buildSystemMetadataContent() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        const Text(
          'UUIDs, highlight colour, and metadata writes for the current setup.',
          style: TextStyle(color: AppColors.muted, height: 1.5),
        ),
        const SizedBox(height: 18),
        const Text(
          'Highlight colour',
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w700,
            color: AppColors.muted,
            letterSpacing: 0.5,
          ),
        ),
        const SizedBox(height: 10),
        ValueListenableBuilder<Color>(
          valueListenable: AppState.highlightColor,
          builder: (context, selectedColor, _) {
            return Wrap(
              spacing: 10,
              runSpacing: 10,
              children: _highlightOptions.map((color) {
                final selected = color.toARGB32() == selectedColor.toARGB32();
                return InkWell(
                  onTap: () {
                    AppState.highlightColor.value = color;
                  },
                  borderRadius: BorderRadius.circular(999),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 180),
                    width: 34,
                    height: 34,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: color,
                      border: Border.all(
                        color: selected
                            ? AppColors.white
                            : Colors.white.withValues(alpha: 0.20),
                        width: selected ? 2.2 : 1.0,
                      ),
                    ),
                  ),
                );
              }).toList(),
            );
          },
        ),
        const SizedBox(height: 14),
        TextField(
          controller: _serviceUuidController,
          onChanged: (value) => AppState.volumeServiceUuid.value = value,
          decoration: const InputDecoration(labelText: 'Service UUID'),
        ),
        const SizedBox(height: 10),
        TextField(
          controller: _volumeCharUuidController,
          onChanged: (value) => AppState.volumeCharUuid.value = value,
          decoration: const InputDecoration(
            labelText: 'Volume characteristic UUID',
          ),
        ),
        const SizedBox(height: 10),
        TextField(
          controller: _metadataCharUuidController,
          onChanged: (value) => AppState.metadataCharUuid.value = value,
          decoration: const InputDecoration(
            labelText: 'Metadata characteristic UUID',
          ),
        ),
        const SizedBox(height: 14),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            OutlinedButton.icon(
              onPressed: () => _syncSelectedOutputToDevice(showSuccess: true),
              icon: const Icon(Icons.route),
              label: const Text('Send output metadata'),
            ),
            FilledButton.icon(
              onPressed: _requestRemoteReboot,
              icon: const Icon(Icons.restart_alt),
              label: const Text('Request RPi reboot'),
            ),
          ],
        ),
      ],
    );
  }
}

class GlassCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;

  const GlassCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(20),
  });

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(28),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 22, sigmaY: 22),
        child: Container(
          padding: padding,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(28),
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                const Color(0xE515171B),
                const Color(0xD9111317),
                const Color(0xE0181B20),
              ],
            ),
            border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
            boxShadow: [
              BoxShadow(
                color: AppColors.shadow.withValues(alpha: 0.72),
                blurRadius: 34,
                offset: Offset(0, 24),
              ),
            ],
          ),
          child: child,
        ),
      ),
    );
  }
}

class SignalBackground extends StatelessWidget {
  final Color accent;

  const SignalBackground({super.key, required this.accent});

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: _SignalBackgroundPainter(accent: accent),
      child: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: const [
              Color(0xFF020202),
              Color(0xFF080809),
              Color(0xFF020203),
            ],
          ),
        ),
      ),
    );
  }
}

class _SignalBackgroundPainter extends CustomPainter {
  final Color accent;

  const _SignalBackgroundPainter({required this.accent});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width * 0.72, size.height * 0.28);
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 18);

    for (var index = 0; index < 5; index++) {
      final radius = 90.0 + (index * 42.0);
      final arcColor = index.isEven ? accent : shiftLightness(accent, 0.10);
      paint
        ..strokeWidth = 22 - (index * 3)
        ..color = arcColor.withValues(alpha: 0.22 - (index * 0.028));
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        math.pi * 0.96,
        math.pi * 0.58,
        false,
        paint,
      );
    }

    final pulsePaint = Paint()
      ..shader =
          RadialGradient(
            colors: [
              accent.withValues(alpha: 0.34),
              shiftLightness(accent, 0.15).withValues(alpha: 0.16),
              Colors.transparent,
            ],
          ).createShader(
            Rect.fromCircle(center: center, radius: size.shortestSide * 0.42),
          );
    canvas.drawCircle(center, size.shortestSide * 0.28, pulsePaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _CardHeading extends StatelessWidget {
  final String eyebrow;
  final String title;
  final String subtitle;
  final Color accent;

  const _CardHeading({
    required this.eyebrow,
    required this.title,
    required this.subtitle,
    this.accent = AppColors.goldBright,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          eyebrow.toUpperCase(),
          style: TextStyle(
            color: accent,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.8,
            fontSize: 12,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          title,
          style: Theme.of(context).textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.w700,
            letterSpacing: -0.4,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          subtitle,
          style: const TextStyle(color: AppColors.muted, height: 1.5),
        ),
      ],
    );
  }
}

class _StatusChip extends StatelessWidget {
  final String label;
  final Color color;
  final IconData icon;

  const _StatusChip({
    required this.label,
    required this.color,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        color: color.withValues(alpha: 0.14),
        border: Border.all(color: color.withValues(alpha: 0.34)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 7),
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: color,
                fontWeight: FontWeight.w700,
                fontSize: 13,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _MetricChip extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color accent;

  const _MetricChip({
    required this.label,
    required this.icon,
    this.accent = AppColors.gold,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        color: Colors.white.withValues(alpha: 0.05),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 15, color: accent),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}

class _DiagnosticMetric {
  final String label;
  final String value;

  const _DiagnosticMetric({required this.label, required this.value});
}

bool _isVocalPointDevice(BleDevice device) {
  final name = device.name?.trim().toLowerCase() ?? '';
  return name.contains('vocalpoint');
}

bool _isNamedDevice(BleDevice device) {
  final name = device.name?.trim() ?? '';
  return name.isNotEmpty && name != 'Unnamed';
}
