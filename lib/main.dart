import 'package:flutter/material.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'vocalpoint',
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color.fromARGB(255, 54, 0, 95),
        ),
      ),
      home: const MyHomePage(title: 'Home'),
        routes: {
          '/bluetooth': (context) => const BluetoothPage(),
          '/volume': (context) => const VolumePage(),
        },
    );
  }
}

class MyHomePage extends StatefulWidget {
  const MyHomePage({super.key, required this.title});
  final String title;

  @override
  State<MyHomePage> createState() => _MyHomePageState();
}

class _MyHomePageState extends State<MyHomePage> {
  bool _loading = false;

  // 🔽 Add your product image path here
  static const String _heroImageAsset = 'assets/product.png';
  // Alternatively, you can use a network image:
  // static const String _heroImageUrl = 'https://example.com/your-product.jpg';

  final List<_FeatureItem> _features = const [
    _FeatureItem(icon: Icons.bluetooth, label: 'Bluetooth Settings', route: '/bluetooth'),
    _FeatureItem(icon: Icons.volume_up_outlined, label: 'Volume Settings', route: '/volume'),
  ];

  Future<void> _refresh() async {
    setState(() => _loading = true);
    await Future<void>.delayed(const Duration(milliseconds: 900));
    if (mounted) setState(() => _loading = false);
  }

  void _onFeatureTap(_FeatureItem item) {
    Navigator.of(context).pushNamed(item.route);
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _refresh,
          child: CustomScrollView(
            physics: const BouncingScrollPhysics(
              parent: AlwaysScrollableScrollPhysics(),
            ),
            slivers: [
              // 🔽 Product image above everything
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.only(top: 12, left: 16, right: 16),
                  child: Center(
                    child: Image.asset(
                      _heroImageAsset, // 'assets/product.png'
                      fit: BoxFit.contain,        // show the whole picture
                      alignment: Alignment.center, 
                      // Optional: keep UI usable if asset missing
                      errorBuilder: (context, err, stack) =>
                          const Text('Image not found', style: TextStyle(fontSize: 16)),
                    ),
                  ),
                ),
              ),

              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 24, 16, 8),
                  child: Text(
                    'Welcome, explore your hearable settings:',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                sliver: SliverLayoutBuilder(
                  builder: (context, constraints) {
                    final crossAxisCount = _gridCountFor(constraints.crossAxisExtent);
                    return SliverGrid(
                      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                        crossAxisCount: crossAxisCount,
                        mainAxisSpacing: 12,
                        crossAxisSpacing: 12,
                        childAspectRatio: 1.1,
                      ),
                      delegate: SliverChildBuilderDelegate(
                        (context, index) {
                          final item = _features[index];
                          return _FeatureCard(item: item, onTap: () => _onFeatureTap(item));
                        },
                        childCount: _features.length,
                      ),
                    );
                  },
                ),
              ),
              const SliverToBoxAdapter(child: SizedBox(height: 96)),
            ],
          ),
        ),
      ),
    );
  }
}

/* --- Helpers & widgets --- */

class _FeatureItem {
  final IconData icon;
  final String label;
  final String route;
  const _FeatureItem({required this.icon, required this.label, required this.route});
}

int _gridCountFor(double width) {
  if (width >= 1200) return 6;
  if (width >= 900) return 5;
  if (width >= 700) return 4;
  if (width >= 520) return 3;
  if (width >= 360) return 2;
  return 1;
}

class _FeatureCard extends StatelessWidget {
  final _FeatureItem item;
  final VoidCallback onTap;
  const _FeatureCard({required this.item, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Material(
      color: cs.surfaceContainerHighest,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: cs.primaryContainer,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(item.icon, color: cs.onPrimaryContainer),
              ),
              const Spacer(),
              Text(item.label, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              Text(
                item.route,
                style: Theme.of(context)
                    .textTheme
                    .labelSmall
                    ?.copyWith(color: cs.onSurfaceVariant),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class BluetoothPage extends StatelessWidget {
  const BluetoothPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Bluetooth Settings')),
      body: const Center(child: Text('Bluetooth controls go here')),
    );
  }
}

class VolumePage extends StatefulWidget {
  const VolumePage({super.key});

  @override
  State<VolumePage> createState() => _VolumePageState();
}

class _VolumePageState extends State<VolumePage> {
  double _volume = 0.5;

  // Optional: if integrating with an audio player, inject it or create it here.
  // final _player = AudioPlayer();

  @override
  void initState() {
    super.initState();
    // If using a player, initialize volume from it:
    // _volume = _player.volume;
  }

  @override
  void dispose() {
    // _player.dispose(); // if you created one here
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Volume')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text(
                  'Adjust Volume',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 16),

                // Slider row (mute icon — slider — loud icon)
                Row(
                  children: [
                    Icon(
                      _volume == 0 ? Icons.volume_mute : Icons.volume_down,
                      semanticLabel: 'Volume low',
                    ),
                    Expanded(
                      child: SliderTheme(
                        data: SliderTheme.of(context).copyWith(
                          trackHeight: 6,
                          thumbShape: const RoundSliderThumbShape(
                            enabledThumbRadius: 10,
                          ),
                          overlayShape: const RoundSliderOverlayShape(
                            overlayRadius: 18,
                          ),
                          valueIndicatorTextStyle: const TextStyle(
                            color: Colors.white,
                          ),
                        ),
                        child: Slider.adaptive(
                          value: _volume,
                          min: 0.0,
                          max: 1.0,
                          divisions: 20, // steps of 0.05
                          label: (_volume * 100).round().toString(),
                          onChanged: (v) {
                            setState(() => _volume = v);
                            // If using an audio player:
                            // _player.setVolume(v);
                          },
                        ),
                      ),
                    ),
                    const Icon(Icons.volume_up, semanticLabel: 'Volume high'),
                  ],
                ),
                const SizedBox(height: 8),

                // Numeric readout + quick actions
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('$_prettyPercent',
                        style: Theme.of(context).textTheme.bodyMedium),
                    Wrap(
                      spacing: 8,
                      children: [
                        _PresetChip(label: 'Mute', onTap: () => _setVolume(0.0)),
                        _PresetChip(label: '50%', onTap: () => _setVolume(0.5)),
                        _PresetChip(label: '100%', onTap: () => _setVolume(1.0)),
                      ],
                    )
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String get _prettyPercent => '${(_volume * 100).round()}%';

  void _setVolume(double v) {
    setState(() => _volume = v);
    // If using an audio player:
    // _player.setVolume(v);
  }
}

class _PresetChip extends StatelessWidget {
  const _PresetChip({required this.label, required this.onTap});
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ActionChip(
      label: Text(label),
      onPressed: onTap,
      tooltip: 'Set volume to $label',
    );
  }
}

