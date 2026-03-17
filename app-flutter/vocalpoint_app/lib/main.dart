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
  static const Color glassWarm = Color(0x33E3B545);
  static const Color outline = Color(0x33FFFFFF);
  static const Color shadow = Color(0x99000000);

  static const Color gold = Color(0xFFE3B545);
  static const Color goldBright = Color(0xFFF4D16D);
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
  static final ValueNotifier<List<RememberedDevice>> rememberedDevices =
      ValueNotifier<List<RememberedDevice>>(<RememberedDevice>[]);

  static final ValueNotifier<String?> connectedDeviceId =
      ValueNotifier<String?>(null);
  static final ValueNotifier<String?> connectedDeviceName =
      ValueNotifier<String?>(null);

  static final ValueNotifier<double> volume = ValueNotifier<double>(50);
  static final ValueNotifier<double> battery = ValueNotifier<double>(75);
  static final ValueNotifier<bool> isMuted = ValueNotifier<bool>(false);
  static final ValueNotifier<Color> highlightColor = ValueNotifier<Color>(
    AppColors.gold,
  );

  static final ValueNotifier<String> bleAddress = ValueNotifier<String>('');
  static final ValueNotifier<String?> audioOutputDeviceName =
      ValueNotifier<String?>(null);
  static final ValueNotifier<String> param1 = ValueNotifier<String>(
    'Morning Tide',
  );
  static final ValueNotifier<String> param2 = ValueNotifier<String>(
    'Amber Lantern',
  );

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
  }

  static void clearOutputSelection() {
    bleAddress.value = '';
    audioOutputDeviceName.value = null;
    param1.value = 'Morning Tide';
  }
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

enum ProfileMenuAction { profile, deviceSettings, about }

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
  static const List<String> _param2Options = <String>[
    'Amber Lantern',
    'Static Bloom',
    'Copper Atlas',
  ];
  static const List<Color> _highlightOptions = <Color>[
    Color(0xFFE3B545),
    Color(0xFFFF9F1C),
    Color(0xFFFF7A1A),
    Color(0xFFE76F51),
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
  Timer? _splashEndTimer;
  Timer? _dashboardTimer;
  Timer? _scanTimeoutTimer;
  Timer? _volumeWriteDebounce;
  Timer? _batteryWriteDebounce;

  bool _showSplashOverlay = true;
  bool _expandSplashLogo = false;
  bool _dashboardUnlocked = false;
  bool _showDashboard = false;
  bool _isScanning = false;
  bool _showDiagnosticsDetails = false;

  SetupPanel? _expandedPanel;
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
    _splashEndTimer?.cancel();
    _dashboardTimer?.cancel();
    _scanTimeoutTimer?.cancel();
    _volumeWriteDebounce?.cancel();
    _batteryWriteDebounce?.cancel();

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
    _splashStartTimer = Timer(const Duration(milliseconds: 900), () {
      if (!mounted) return;
      setState(() => _expandSplashLogo = true);
    });

    _splashEndTimer = Timer(const Duration(milliseconds: 1500), () {
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
      setState(() => _dashboardUnlocked = true);
      _dashboardTimer?.cancel();
      _dashboardTimer = Timer(const Duration(milliseconds: 700), () {
        if (!mounted) return;
        setState(() {
          _showDashboard = true;
          _expandedPanel = null;
        });
      });
    }

    if (!ready && !_dashboardUnlocked && mounted) {
      setState(() => _showDashboard = false);
    }
  }

  Future<void> _skipToDashboard() async {
    if (_isScanning) {
      await _stopScan();
    }
    if (!mounted) return;
    setState(() {
      _dashboardUnlocked = true;
      _showDashboard = true;
      _expandedPanel = null;
    });
  }

  bool get _hasConnectedVocalPoint => AppState.connectedDeviceId.value != null;
  bool get _hasSelectedOutputDevice => AppState.bleAddress.value.isNotEmpty;

  bool _hasDisplayName(BleDevice device) {
    final name = device.name?.trim() ?? '';
    return name.isNotEmpty && name != 'Unnamed';
  }

  bool _isSelectableOutput(BleDevice device) {
    return _isNamedDevice(device) && !_isVocalPointDevice(device);
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
    final name = device.name?.trim().isNotEmpty == true
        ? device.name!.trim()
        : device.deviceId;
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
    final name = device.name?.trim().isNotEmpty == true
        ? device.name!.trim()
        : 'Unnamed device';

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
      await _writeBatteryToDevice();
      await _syncSelectedOutputToDevice(showSuccess: false);
      await _sendParam2(AppState.param2.value, showSuccess: false);

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

    AppState.clearConnection();
    if (mounted) {
      setState(() => _pendingVocalPointId = null);
    }
    _showToast('Disconnected VocalPoint device');
  }

  Future<void> _selectOutputDevice(BleDevice device) async {
    final name = device.name?.trim().isNotEmpty == true
        ? device.name!.trim()
        : device.deviceId;

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

  Future<void> _writeBatteryToDevice({bool showSuccess = false}) async {
    final battery = AppState.battery.value.round().clamp(0, 100);
    await _writeMetadataToken(
      'BATTERY=$battery',
      showSuccess: showSuccess,
      successMessage: 'Sent BATTERY=$battery',
    );
  }

  Future<void> _syncSelectedOutputToDevice({bool showSuccess = true}) async {
    final address = AppState.bleAddress.value.trim();
    final outputName = AppState.audioOutputDeviceName.value?.trim() ?? '';

    if (address.isEmpty || outputName.isEmpty) {
      if (showSuccess) {
        _showToast('Select an output device first');
      }
      return;
    }

    await _writeMetadataToken('BLE_ADDR=$address', showSuccess: false);
    await _writeMetadataToken('PARAM1=$outputName', showSuccess: false);

    if (showSuccess) {
      _showToast('Sent BLE_ADDR and PARAM1');
    }
  }

  Future<void> _sendParam2(String value, {bool showSuccess = true}) async {
    AppState.param2.value = value;
    await _writeMetadataToken(
      'PARAM2=$value',
      showSuccess: showSuccess,
      successMessage: 'Sent PARAM2=$value',
    );
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

  void _onBatteryChanged(double value) {
    AppState.battery.value = value;
    _batteryWriteDebounce?.cancel();
    _batteryWriteDebounce = Timer(
      const Duration(milliseconds: 160),
      () => _writeBatteryToDevice(),
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
      case ProfileMenuAction.profile:
        _showToast('Profile menu is a placeholder for now');
      case ProfileMenuAction.deviceSettings:
        setState(() => _showDiagnosticsDetails = true);
        _showToast('Device settings are available in diagnostics');
      case ProfileMenuAction.about:
        showAboutDialog(
          context: context,
          applicationName: 'VocalPoint',
          applicationVersion: '1.0.0',
          children: const [
            Text(
              'Glassy BLE controller for VocalPoint and external output devices.',
            ),
          ],
        );
    }
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
          SafeArea(
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 650),
              switchInCurve: Curves.easeOutCubic,
              switchOutCurve: Curves.easeInCubic,
              transitionBuilder: (child, animation) {
                return FadeTransition(
                  opacity: animation,
                  child: SlideTransition(
                    position: Tween<Offset>(
                      begin: const Offset(0, 0.03),
                      end: Offset.zero,
                    ).animate(animation),
                    child: child,
                  ),
                );
              },
              child: _showDashboard
                  ? _buildDashboardView(context)
                  : _buildSetupView(context),
            ),
          ),
          if (_showSplashOverlay) _buildSplashOverlay(),
        ],
      ),
    );
  }

  Widget _buildSplashOverlay() {
    return Positioned.fill(
      child: IgnorePointer(
        child: AnimatedOpacity(
          opacity: _showSplashOverlay ? 1 : 0,
          duration: const Duration(milliseconds: 260),
          child: Container(
            color: Colors.black,
            alignment: Alignment.center,
            child: TweenAnimationBuilder<double>(
              tween: Tween<double>(begin: 1, end: _expandSplashLogo ? 18 : 1),
              duration: const Duration(milliseconds: 700),
              curve: Curves.easeInCubic,
              builder: (context, value, child) {
                return Transform.scale(scale: value, child: child);
              },
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
                padding: const EdgeInsets.fromLTRB(16, 20, 16, 56),
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: maxWidth),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _buildTopBar(showBackToDashboard: _dashboardUnlocked),
                      const SizedBox(height: 28),
                      GlassCard(
                        padding: const EdgeInsets.fromLTRB(24, 24, 24, 26),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Build your signal chain',
                              style: Theme.of(context).textTheme.headlineMedium
                                  ?.copyWith(
                                    fontWeight: FontWeight.w800,
                                    letterSpacing: -1.2,
                                  ),
                            ),
                            const SizedBox(height: 12),
                            const Text(
                              'Start by pairing VocalPoint and choosing where audio should land. Once both links are ready, the control surface opens automatically.',
                              style: TextStyle(
                                color: AppColors.muted,
                                height: 1.45,
                                fontSize: 15,
                              ),
                            ),
                            const SizedBox(height: 24),
                            _buildConnectionPanel(SetupPanel.vocalPoint),
                            const SizedBox(height: 20),
                            _buildConnectionPanel(SetupPanel.output),
                            if (_dashboardUnlocked && !_showDashboard) ...[
                              const SizedBox(height: 24),
                              FilledButton.icon(
                                onPressed: () =>
                                    setState(() => _showDashboard = true),
                                style: FilledButton.styleFrom(
                                  backgroundColor: _highlightColor,
                                  foregroundColor: Colors.black,
                                  padding: const EdgeInsets.symmetric(
                                    vertical: 18,
                                  ),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(20),
                                  ),
                                ),
                                icon: const Icon(Icons.waves),
                                label: const Text('Enter control surface'),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              Positioned(
                right: 8,
                bottom: 6,
                child: TextButton(
                  onPressed: _skipToDashboard,
                  style: TextButton.styleFrom(
                    foregroundColor: AppColors.white.withValues(alpha: 0.45),
                    textStyle: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      letterSpacing: 0.3,
                    ),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 8,
                    ),
                  ),
                  child: const Text('Skip'),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildDashboardView(BuildContext context) {
    return LayoutBuilder(
      key: const ValueKey<String>('dashboard-view'),
      builder: (context, constraints) {
        final contentWidth = math.min(constraints.maxWidth - 32, 1100.0);
        final wide = contentWidth > 760;
        final cardWidth = wide ? (contentWidth - 12) / 2 : contentWidth;
        final heroHeight = math.max(
          300.0,
          math.min(420.0, constraints.maxHeight * 0.48),
        );

        return Align(
          alignment: Alignment.topCenter,
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(16, 20, 16, 28),
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: contentWidth),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _buildTopBar(showBackToDashboard: false),
                  const SizedBox(height: 22),
                  SizedBox(
                    height: heroHeight,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        ConstrainedBox(
                          constraints: BoxConstraints(
                            maxWidth: wide ? 620 : contentWidth,
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Welcome back',
                                style: Theme.of(context).textTheme.displaySmall
                                    ?.copyWith(
                                      fontWeight: FontWeight.w800,
                                      letterSpacing: -1.8,
                                    ),
                              ),
                              const SizedBox(height: 12),
                              const Text(
                                'Your VocalPoint path is live. Tune output, monitor the device, and send control values to the ESP32 without leaving this surface.',
                                style: TextStyle(
                                  color: AppColors.muted,
                                  height: 1.55,
                                  fontSize: 16,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 22),
                        Wrap(
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
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      SizedBox(
                        width: cardWidth,
                        child: _buildVolumeCard(context),
                      ),
                      SizedBox(
                        width: cardWidth,
                        child: _buildDeviceCard(context),
                      ),
                      SizedBox(
                        width: cardWidth,
                        child: _buildVoiceMixCard(context),
                      ),
                      SizedBox(
                        width: cardWidth,
                        child: _buildDiagnosticsCard(context),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildTopBar({required bool showBackToDashboard}) {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'VocalPoint',
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.w700,
                  letterSpacing: 2.4,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                showBackToDashboard
                    ? 'Connection setup'
                    : (_showDashboard ? 'Control surface' : 'Connection setup'),
                style: const TextStyle(
                  color: AppColors.mutedSoft,
                  letterSpacing: 0.6,
                ),
              ),
            ],
          ),
        ),
        if (showBackToDashboard)
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: TextButton.icon(
              onPressed: () => setState(() => _showDashboard = true),
              icon: const Icon(Icons.dashboard_customize_outlined),
              label: const Text('Dashboard'),
            ),
          ),
        PopupMenuButton<ProfileMenuAction>(
          onSelected: _handleProfileMenu,
          color: AppColors.panelSoft.withValues(alpha: 0.97),
          itemBuilder: (context) => const [
            PopupMenuItem(
              value: ProfileMenuAction.profile,
              child: Text('Profile'),
            ),
            PopupMenuItem(
              value: ProfileMenuAction.deviceSettings,
              child: Text('Device settings'),
            ),
            PopupMenuItem(value: ProfileMenuAction.about, child: Text('About')),
          ],
          child: Container(
            width: 68,
            height: 68,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: Colors.white.withValues(alpha: 0.06),
              border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
            ),
            padding: const EdgeInsets.all(16),
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
  }

  Widget _buildConnectionPanel(SetupPanel panel) {
    final accent = _highlightColor;
    final isVocalPoint = panel == SetupPanel.vocalPoint;
    final isExpanded = _expandedPanel == panel;
    final isScanning = _isScanning && _activeScanTarget == panel;
    final isConnected = isVocalPoint
        ? _hasConnectedVocalPoint
        : _hasSelectedOutputDevice;
    final isConnecting = isVocalPoint
        ? _pendingVocalPointId != null
        : _pendingOutputId != null;
    final title = isVocalPoint
        ? 'Connect to VocalPoint'
        : 'Connect to Output Device';
    final subtitle = isVocalPoint
        ? 'Pair with the ESP32 controller that receives your commands.'
        : 'Pick the headphone, speaker, or listening target that VocalPoint will route to.';
    final status = isConnected
        ? (isVocalPoint
              ? (AppState.connectedDeviceName.value ?? 'Connected')
              : (AppState.audioOutputDeviceName.value ?? 'Selected'))
        : (isConnecting ? 'Connecting...' : 'Not connected');
    final actionLabel = isScanning
        ? 'Scanning...'
        : (isVocalPoint
              ? 'Scan for VocalPoint devices'
              : 'Scan for output devices');
    final results = isVocalPoint ? _vocalPointResults : _outputResults;

    return AnimatedSize(
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeOutCubic,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Column(
              children: [
                GestureDetector(
                  onTap: () => _openPanel(panel),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 350),
                    curve: Curves.easeOutCubic,
                    width: 176,
                    height: 176,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: isConnected
                          ? const Color(0xFF13905A)
                          : (isExpanded || isScanning
                                ? const Color(0xFF1A1B1F)
                                : const Color(0xFF111216)),
                      border: Border.all(
                        color: Colors.black.withValues(alpha: 0.88),
                        width: isExpanded || isScanning ? 1.8 : 1.4,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.34),
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
                            width: 148,
                            height: 148,
                            child: CircularProgressIndicator(
                              strokeWidth: 2.6,
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
                              size: 34,
                              color: AppColors.white,
                            ),
                            const SizedBox(height: 10),
                            Padding(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 18,
                              ),
                              child: Text(
                                title,
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                  fontSize: 17,
                                  fontWeight: FontWeight.w700,
                                  height: 1.2,
                                ),
                              ),
                            ),
                            const SizedBox(height: 10),
                            TextButton(
                              onPressed: () => _openPanel(panel),
                              style: TextButton.styleFrom(
                                padding: EdgeInsets.zero,
                                minimumSize: Size.zero,
                                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                foregroundColor: Colors.white.withValues(
                                  alpha: isConnected ? 0.78 : 0.54,
                                ),
                              ),
                              child: Text(
                                isConnected
                                    ? 'tap to change'
                                    : (isConnecting
                                          ? 'connecting...'
                                          : 'tap to open'),
                                style: TextStyle(
                                  fontSize: 12.5,
                                  letterSpacing: 0.6,
                                  color: Colors.white.withValues(
                                    alpha: isConnected ? 0.78 : 0.54,
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  status,
                  textAlign: TextAlign.center,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 6),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  child: Text(
                    subtitle,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: AppColors.muted,
                      height: 1.45,
                    ),
                  ),
                ),
              ],
            ),
          ),
          if (isExpanded) ...[
            const SizedBox(height: 18),
            GlassCard(
              padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
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
                              ?.copyWith(fontWeight: FontWeight.w700),
                        ),
                      ),
                      Wrap(
                        spacing: 10,
                        runSpacing: 10,
                        children: [
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
                          OutlinedButton.icon(
                            onPressed: isScanning ? _stopScan : null,
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
                  if (results.isEmpty)
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
    );
  }

  Widget _buildSelectedSummary(SetupPanel panel) {
    final accent = _highlightColor;
    final accentBright = _highlightBright;
    final isVocalPoint = panel == SetupPanel.vocalPoint;
    final selectedName = isVocalPoint
        ? AppState.connectedDeviceName.value
        : AppState.audioOutputDeviceName.value;
    final selectedId = isVocalPoint
        ? AppState.connectedDeviceId.value
        : AppState.bleAddress.value;
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
                        const SizedBox(height: 4),
                        Text(
                          isReady
                              ? (selectedId == null || selectedId.isEmpty
                                    ? 'Identifier unavailable'
                                    : selectedId)
                              : (isVocalPoint
                                    ? 'Pick the VocalPoint controller first.'
                                    : 'Pick an output target first.'),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(color: AppColors.muted),
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
                const SizedBox(height: 4),
                Text(
                  device.deviceId,
                  style: const TextStyle(
                    color: AppColors.mutedSoft,
                    fontSize: 12.5,
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

  Widget _buildVolumeCard(BuildContext context) {
    final accent = _highlightColor;
    final accentBright = _highlightBright;
    return GlassCard(
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
          const SizedBox(height: 18),
          ValueListenableBuilder<bool>(
            valueListenable: AppState.isMuted,
            builder: (context, muted, _) {
              return ValueListenableBuilder<double>(
                valueListenable: AppState.volume,
                builder: (context, volume, __) {
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          _MetricChip(
                            label: 'Volume ${volume.round()}',
                            icon: Icons.tune,
                            accent: accentBright,
                          ),
                          const SizedBox(width: 10),
                          _MetricChip(
                            label: muted ? 'Muted' : 'Live',
                            icon: muted ? Icons.volume_off : Icons.volume_up,
                            accent: muted
                                ? AppColors.danger
                                : AppColors.success,
                          ),
                        ],
                      ),
                      const SizedBox(height: 18),
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
    );
  }

  Widget _buildDeviceCard(BuildContext context) {
    final accent = _highlightColor;
    final accentBright = _highlightBright;
    return GlassCard(
      padding: const EdgeInsets.all(22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _CardHeading(
            eyebrow: 'Devices',
            title: 'Input and output routing',
            subtitle:
                'Monitor the active BLE controller and selected output target. You can drop back into setup at any time.',
            accent: accentBright,
          ),
          const SizedBox(height: 18),
          _DeviceStatusRow(
            icon: Icons.graphic_eq,
            title: 'VocalPoint controller',
            name: AppState.connectedDeviceName.value ?? 'Not connected',
            detail:
                AppState.connectedDeviceId.value ??
                'No BLE controller selected',
            connected: _hasConnectedVocalPoint,
          ),
          const SizedBox(height: 12),
          _DeviceStatusRow(
            icon: Icons.headphones,
            title: 'Output device',
            name: AppState.audioOutputDeviceName.value ?? 'Not selected',
            detail: AppState.bleAddress.value.isEmpty
                ? 'No output target selected'
                : AppState.bleAddress.value,
            connected: _hasSelectedOutputDevice,
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              OutlinedButton.icon(
                onPressed: () => setState(() {
                  _showDashboard = false;
                  _expandedPanel = SetupPanel.vocalPoint;
                }),
                icon: const Icon(Icons.bluetooth_searching),
                label: const Text('Change VocalPoint'),
              ),
              OutlinedButton.icon(
                onPressed: () => setState(() {
                  _showDashboard = false;
                  _expandedPanel = SetupPanel.output;
                }),
                icon: const Icon(Icons.speaker_group),
                label: const Text('Change output'),
              ),
              FilledButton.icon(
                onPressed: _hasConnectedVocalPoint
                    ? () => _syncSelectedOutputToDevice(showSuccess: true)
                    : null,
                style: FilledButton.styleFrom(
                  backgroundColor: accent,
                  foregroundColor: Colors.black,
                ),
                icon: const Icon(Icons.sync),
                label: const Text('Sync routing'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildVoiceMixCard(BuildContext context) {
    final accent = _highlightColor;
    final accentBright = _highlightBright;
    return GlassCard(
      padding: const EdgeInsets.all(22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _CardHeading(
            eyebrow: 'Mix',
            title: 'Voice balance',
            subtitle:
                'Dummy control surface for prioritising different voices. PARAM2 still maps to the existing metadata token.',
            accent: accentBright,
          ),
          const SizedBox(height: 18),
          ..._param2Options.map(
            (option) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: InkWell(
                onTap: () => _sendParam2(option),
                borderRadius: BorderRadius.circular(18),
                child: ValueListenableBuilder<String>(
                  valueListenable: AppState.param2,
                  builder: (context, selected, _) {
                    final active = selected == option;
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
                              : Colors.white.withValues(alpha: 0.08),
                        ),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            active
                                ? Icons.multitrack_audio
                                : Icons.person_2_outlined,
                            color: active ? accentBright : AppColors.muted,
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Text(
                              option,
                              style: const TextStyle(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                          if (active)
                            Icon(Icons.check_circle, color: accentBright),
                        ],
                      ),
                    );
                  },
                ),
              ),
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Future voice/person sliders can live here without changing the current BLE transport contract.',
            style: TextStyle(color: AppColors.muted),
          ),
        ],
      ),
    );
  }

  Widget _buildDiagnosticsCard(BuildContext context) {
    final accent = _highlightColor;
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

    return GlassCard(
      padding: const EdgeInsets.all(22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: _CardHeading(
                  eyebrow: 'Diagnostics',
                  title: 'System and metadata',
                  subtitle:
                      'UUIDs, battery writes, and transport state for the current setup.',
                  accent: accentBright,
                ),
              ),
              IconButton(
                onPressed: () => setState(() {
                  _showDiagnosticsDetails = !_showDiagnosticsDetails;
                }),
                icon: Icon(
                  _showDiagnosticsDetails
                      ? Icons.expand_less
                      : Icons.expand_more,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
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
          const SizedBox(height: 16),
          ValueListenableBuilder<double>(
            valueListenable: AppState.battery,
            builder: (context, battery, _) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Battery mirror ${battery.round()}%',
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                  SliderTheme(
                    data: SliderTheme.of(context).copyWith(
                      activeTrackColor: accent,
                      inactiveTrackColor: Colors.white.withValues(alpha: 0.12),
                      thumbColor: accentBright,
                      overlayColor: accent.withValues(alpha: 0.16),
                      trackHeight: 4,
                    ),
                    child: Slider(
                      value: battery,
                      min: 0,
                      max: 100,
                      divisions: 100,
                      onChanged: _onBatteryChanged,
                    ),
                  ),
                ],
              );
            },
          ),
          AnimatedCrossFade(
            duration: const Duration(milliseconds: 240),
            crossFadeState: _showDiagnosticsDetails
                ? CrossFadeState.showSecond
                : CrossFadeState.showFirst,
            firstChild: Row(
              children: [
                FilledButton.icon(
                  onPressed: () => _writeBatteryToDevice(showSuccess: true),
                  style: FilledButton.styleFrom(
                    backgroundColor: accent,
                    foregroundColor: Colors.black,
                  ),
                  icon: const Icon(Icons.battery_charging_full),
                  label: const Text('Send battery'),
                ),
              ],
            ),
            secondChild: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
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
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: _highlightOptions.map((color) {
                    final selected =
                        color.toARGB32() == _highlightColor.toARGB32();
                    return InkWell(
                      onTap: () {
                        setState(() {
                          AppState.highlightColor.value = color;
                        });
                      },
                      borderRadius: BorderRadius.circular(999),
                      child: Container(
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
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: _serviceUuidController,
                  onChanged: (value) =>
                      AppState.volumeServiceUuid.value = value,
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
                    FilledButton.icon(
                      onPressed: () => _writeBatteryToDevice(showSuccess: true),
                      style: FilledButton.styleFrom(
                        backgroundColor: accent,
                        foregroundColor: Colors.black,
                      ),
                      icon: const Icon(Icons.battery_full),
                      label: const Text('Send battery'),
                    ),
                    OutlinedButton.icon(
                      onPressed: () =>
                          _syncSelectedOutputToDevice(showSuccess: true),
                      icon: const Icon(Icons.route),
                      label: const Text('Send output metadata'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
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

class _DeviceStatusRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String name;
  final String detail;
  final bool connected;

  const _DeviceStatusRow({
    required this.icon,
    required this.title,
    required this.name,
    required this.detail,
    required this.connected,
  });

  @override
  Widget build(BuildContext context) {
    final inactiveAccent = AppState.highlightColor.value;
    final inactiveAccentBright = shiftLightness(inactiveAccent, 0.14);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(18),
        color: Colors.white.withValues(alpha: 0.05),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: (connected ? AppColors.success : inactiveAccent)
                  .withValues(alpha: 0.16),
            ),
            child: Icon(
              icon,
              color: connected ? AppColors.success : inactiveAccentBright,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(color: AppColors.muted, fontSize: 13),
                ),
                const SizedBox(height: 4),
                Text(
                  name,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 16,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  detail,
                  style: const TextStyle(
                    color: AppColors.mutedSoft,
                    fontSize: 12.5,
                  ),
                ),
              ],
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
