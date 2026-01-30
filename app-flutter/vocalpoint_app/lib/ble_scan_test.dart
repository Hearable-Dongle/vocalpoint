import 'package:flutter/material.dart';
import 'package:universal_ble/universal_ble.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(home: BleTestPage());
  }
}

class BleTestPage extends StatefulWidget {
  const BleTestPage({super.key});

  @override
  State<BleTestPage> createState() => _BleTestPageState();
}

class _BleTestPageState extends State<BleTestPage> {
  final List<BleDevice> devices = [];

  @override
  void initState() {
    super.initState();

    UniversalBle.onScanResult = (device) {
      if (!devices.any((d) => d.deviceId == device.deviceId)) {
        setState(() => devices.add(device));
      }
    };
  }

  void startScan() async {
    devices.clear();
    await UniversalBle.startScan();
  }

  void stopScan() async {
    await UniversalBle.stopScan();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("macOS BLE Test")),
      body: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              ElevatedButton(onPressed: startScan, child: const Text("Scan")),
              const SizedBox(width: 16),
              ElevatedButton(onPressed: stopScan, child: const Text("Stop")),
            ],
          ),
          Expanded(
            child: ListView.builder(
              itemCount: devices.length,
              itemBuilder: (_, i) {
                final d = devices[i];
                return ListTile(
                  title: Text(d.name ?? "Unnamed"),
                  subtitle: Text(d.deviceId),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}