import UIKit
import ARKit
import AVFoundation
import CoreMotion

final class ARMeasureViewController: UIViewController, ARSCNViewDelegate {
    var onComplete: (([String: Any]) -> Void)?
    var onCancel: (() -> Void)?

    private let sceneView = ARSCNView()
    private let reticle = UIView()
    private let statusLabel = UILabel()
    private let metaLabel = UILabel()
    private let confidenceBar = UIView()
    private let confidenceFill = UIView()
    private var setAButton = UIButton(type: .system)
    private var setBButton = UIButton(type: .system)
    private var torchButton = UIButton(type: .system)
    private var cancelButton = UIButton(type: .system)
    private var forceButton = UIButton(type: .system)

    private var pointA: SIMD3<Float>?
    private var samples: [SIMD3<Float>] = []
    private var sampling = false
    private var sampleTarget = 12
    private var torchOn = false
    private var lastHit: SIMD3<Float>?
    private var lastConfidence: Float = 0
    private let haptic = UINotificationFeedbackGenerator()
    private var didBuzzLevel = false
    private let lidar = ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh)
    private let altimeter = CMAltimeter()
    private var altitudeA: Double?
    private var altitudeNow: Double?

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor(red: 0.04, green: 0.05, blue: 0.06, alpha: 1)
        sceneView.delegate = self
        sceneView.automaticallyUpdatesLighting = true
        sceneView.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(sceneView)

        reticle.layer.borderColor = UIColor(red: 0.16, green: 0.47, blue: 1, alpha: 1).cgColor
        reticle.layer.borderWidth = 3
        reticle.backgroundColor = .clear
        reticle.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(reticle)

        configureLabel(statusLabel, size: 22, bold: true)
        configureLabel(metaLabel, size: 13, bold: false)
        confidenceBar.backgroundColor = UIColor.white.withAlphaComponent(0.12)
        confidenceFill.backgroundColor = UIColor(red: 0, green: 0.9, blue: 0.46, alpha: 1)
        confidenceBar.translatesAutoresizingMaskIntoConstraints = false
        confidenceFill.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(confidenceBar)
        confidenceBar.addSubview(confidenceFill)

        setAButton = pill("SET POINT A", color: UIColor(red: 0.16, green: 0.47, blue: 1, alpha: 1))
        setBButton = pill("SET POINT B", color: UIColor(red: 0, green: 0.9, blue: 0.46, alpha: 1))
        forceButton = pill("FORCE SNAP", color: UIColor(red: 1, green: 0.84, blue: 0, alpha: 1))
        torchButton = pill("LIGHT", color: UIColor(red: 0.79, green: 0.64, blue: 0.15, alpha: 1))
        cancelButton = pill("CANCEL", color: UIColor(white: 0.35, alpha: 1))
        setBButton.isEnabled = false
        forceButton.isEnabled = false
        setAButton.addTarget(self, action: #selector(tapA), for: .touchUpInside)
        setBButton.addTarget(self, action: #selector(tapB), for: .touchUpInside)
        forceButton.addTarget(self, action: #selector(forceB), for: .touchUpInside)
        torchButton.addTarget(self, action: #selector(toggleTorch), for: .touchUpInside)
        cancelButton.addTarget(self, action: #selector(cancel), for: .touchUpInside)

        let row = UIStackView(arrangedSubviews: [cancelButton, torchButton, setAButton])
        row.axis = .horizontal
        row.spacing = 8
        row.distribution = .fillEqually
        row.translatesAutoresizingMaskIntoConstraints = false
        let row2 = UIStackView(arrangedSubviews: [forceButton, setBButton])
        row2.axis = .horizontal
        row2.spacing = 8
        row2.distribution = .fillEqually
        row2.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(row)
        view.addSubview(row2)

        NSLayoutConstraint.activate([
            sceneView.topAnchor.constraint(equalTo: view.topAnchor),
            sceneView.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            sceneView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            sceneView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            reticle.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            reticle.centerYAnchor.constraint(equalTo: view.centerYAnchor, constant: -24),
            reticle.widthAnchor.constraint(equalToConstant: 28),
            reticle.heightAnchor.constraint(equalToConstant: 28),
            statusLabel.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            statusLabel.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),
            statusLabel.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 12),
            metaLabel.leadingAnchor.constraint(equalTo: statusLabel.leadingAnchor),
            metaLabel.trailingAnchor.constraint(equalTo: statusLabel.trailingAnchor),
            metaLabel.topAnchor.constraint(equalTo: statusLabel.bottomAnchor, constant: 6),
            confidenceBar.leadingAnchor.constraint(equalTo: statusLabel.leadingAnchor),
            confidenceBar.trailingAnchor.constraint(equalTo: statusLabel.trailingAnchor),
            confidenceBar.topAnchor.constraint(equalTo: metaLabel.bottomAnchor, constant: 10),
            confidenceBar.heightAnchor.constraint(equalToConstant: 8),
            confidenceFill.leadingAnchor.constraint(equalTo: confidenceBar.leadingAnchor),
            confidenceFill.topAnchor.constraint(equalTo: confidenceBar.topAnchor),
            confidenceFill.bottomAnchor.constraint(equalTo: confidenceBar.bottomAnchor),
            confidenceFill.widthAnchor.constraint(equalTo: confidenceBar.widthAnchor, multiplier: 0.2),
            row2.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 12),
            row2.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -12),
            row2.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -12),
            row2.heightAnchor.constraint(equalToConstant: 56),
            row.leadingAnchor.constraint(equalTo: row2.leadingAnchor),
            row.trailingAnchor.constraint(equalTo: row2.trailingAnchor),
            row.bottomAnchor.constraint(equalTo: row2.topAnchor, constant: -10),
            row.heightAnchor.constraint(equalToConstant: 56)
        ])
        statusLabel.text = lidar ? "ARKIT + LIDAR · AIM POINT A" : "ARKIT WORLD TRACKING · AIM POINT A (NO LIDAR)"
        metaLabel.text = lidar ? "Native ARKit with LiDAR. Not the browser camera tape." : "Native ARKit world tracking — not LiDAR, not the browser camera tape."
    }

    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        let config = ARWorldTrackingConfiguration()
        config.planeDetection = [.horizontal, .vertical]
        if lidar {
            config.sceneReconstruction = .mesh
            if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
                config.frameSemantics.insert(.sceneDepth)
            }
        }
        config.environmentTexturing = .automatic
        sceneView.session.run(config, options: [.resetTracking, .removeExistingAnchors])
        if CMAltimeter.isRelativeAltitudeAvailable() {
            altimeter.startRelativeAltitudeUpdates(to: .main) { [weak self] data, _ in
                self?.altitudeNow = data?.relativeAltitude.doubleValue
            }
        }
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        sceneView.session.pause()
        altimeter.stopRelativeAltitudeUpdates()
        ARMeasureViewController.setTorch(false)
    }

    func renderer(_ renderer: SCNSceneRenderer, updateAtTime time: TimeInterval) {
        DispatchQueue.main.async {
            guard let hit = self.centerHit() else {
                self.lastHit = nil
                self.lastConfidence = 0.15
                self.updateChrome()
                return
            }
            self.lastHit = hit
            if self.sampling {
                self.samples.append(hit)
                if self.samples.count >= self.sampleTarget {
                    self.finishSampling()
                }
            }
            self.updateChrome()
        }
    }

    private func centerHit() -> SIMD3<Float>? {
        let pt = CGPoint(x: sceneView.bounds.midX, y: sceneView.bounds.midY - 24)
        let types: ARRaycastQuery.Target = lidar ? .existingPlaneGeometry : .estimatedPlane
        if let query = sceneView.raycastQuery(from: pt, allowing: types, alignment: .any) {
            let results = sceneView.session.raycast(query)
            if let first = results.first {
                lastConfidence = min(1, 0.55 + Float(results.count) * 0.08 + (lidar ? 0.25 : 0))
                let c = first.worldTransform.columns.3
                return SIMD3(c.x, c.y, c.z)
            }
        }
        if let fallback = sceneView.hitTest(pt, types: [.existingPlaneUsingExtent, .estimatedHorizontalPlane, .featurePoint]).first {
            lastConfidence = lidar ? 0.7 : 0.42
            let c = fallback.worldTransform.columns.3
            return SIMD3(c.x, c.y, c.z)
        }
        lastConfidence = 0.2
        return nil
    }

    private func updateChrome() {
        guard let a = pointA, let now = lastHit else {
            confidenceFill.transform = CGAffineTransform(scaleX: CGFloat(max(0.08, lastConfidence)), y: 1)
            return
        }
        let dyIn = Double(now.y - a.y) * 39.37007874
        let distFt = Double(simd_distance(now, a)) * 3.280839895
        let level = abs(dyIn) <= 0.125
        view.backgroundColor = level ? UIColor(red: 0, green: 0.9, blue: 0.46, alpha: 0.18) : UIColor.black
        reticle.layer.borderColor = (level ? UIColor(red: 0, green: 0.9, blue: 0.46, alpha: 1) : UIColor(red: 1, green: 0.2, blue: 0.4, alpha: 1)).cgColor
        statusLabel.text = level ? "LEVEL · SNAP B" : String(format: "ΔH %+.3f in  ·  %.2f ft", dyIn, distFt)
        statusLabel.textColor = level ? UIColor(red: 0, green: 0.9, blue: 0.46, alpha: 1) : .white
        if level && !didBuzzLevel {
            haptic.notificationOccurred(.success)
            didBuzzLevel = true
        }
        if !level { didBuzzLevel = false }
        confidenceFill.transform = CGAffineTransform(scaleX: CGFloat(max(0.08, lastConfidence)), y: 1)
        metaLabel.text = String(format: "%@ · confidence %.0f%% · samples %d", lidar ? "ARKit LiDAR" : "ARKit (no LiDAR)", lastConfidence * 100, samples.count)
    }

    @objc private func tapA() { beginSampling(forA: true, force: false) }
    @objc private func tapB() { beginSampling(forA: false, force: false) }
    @objc private func forceB() { beginSampling(forA: false, force: true) }

    private var samplingA = true
    private var forceSnap = false

    private func beginSampling(forA: Bool, force: Bool) {
        guard lastHit != nil || force else { return }
        samplingA = forA
        forceSnap = force
        samples = []
        sampling = true
        statusLabel.text = "SAMPLING…"
        if forA { altitudeA = altitudeNow }
    }

    private func finishSampling() {
        sampling = false
        let avg = samples.reduce(SIMD3<Float>(repeating: 0), +) / Float(samples.count)
        let variance = samples.map { simd_distance($0, avg) }.reduce(0, +) / Float(samples.count)
        let conf = max(0.2, min(1, lastConfidence * (variance < 0.01 ? 1 : 0.7)))
        if samplingA {
            pointA = avg
            setBButton.isEnabled = true
            forceButton.isEnabled = true
            setAButton.setTitle("RESET A", for: .normal)
            statusLabel.text = "POINT A SET · WALK THE LINE"
            haptic.notificationOccurred(.success)
            return
        }
        guard let a = pointA else { return }
        let dyIn = Double(avg.y - a.y) * 39.37007874
        let level = abs(dyIn) <= 0.125
        if !level && !forceSnap {
            statusLabel.text = String(format: "OFF LEVEL %+.3f in — wait for green or FORCE SNAP", dyIn)
            haptic.notificationOccurred(.warning)
            return
        }
        let distFt = Double(simd_distance(avg, a)) * 3.280839895
        let payload: [String: Any] = [
            "point_a": ["x": Double(a.x), "y": Double(a.y), "z": Double(a.z)],
            "point_b": ["x": Double(avg.x), "y": Double(avg.y), "z": Double(avg.z)],
            "distance_ft": distFt,
            "delta_height_in": dyIn,
            "level": level,
            "forced": forceSnap,
            "confidence": Double(conf),
            "sample_count": samples.count,
            "lidar": lidar,
            "engine": lidar ? "arkit-lidar" : "arkit",
            "honesty_label": lidar ? "ARKit with LiDAR" : "ARKit world tracking (no LiDAR)",
            "warning": (!level && forceSnap) ? "Force-snapped off-level" : ""
        ]
        dismiss(animated: true) { self.onComplete?(payload) }
    }

    @objc private func toggleTorch() {
        torchOn.toggle()
        ARMeasureViewController.setTorch(torchOn)
        torchButton.setTitle(torchOn ? "LIGHT ON" : "LIGHT", for: .normal)
    }

    @objc private func cancel() {
        dismiss(animated: true) { self.onCancel?() }
    }

    static func setTorch(_ on: Bool) {
        guard let device = AVCaptureDevice.default(for: .video), device.hasTorch else { return }
        do {
            try device.lockForConfiguration()
            if on, device.isTorchModeSupported(.on) {
                try device.setTorchModeOn(level: 0.85)
            } else {
                device.torchMode = .off
            }
            device.unlockForConfiguration()
        } catch {
            NSLog("BedForge torch failed")
        }
    }

    private func configureLabel(_ label: UILabel, size: CGFloat, bold: Bool) {
        label.translatesAutoresizingMaskIntoConstraints = false
        label.textColor = .white
        label.numberOfLines = 2
        label.font = UIFont(name: bold ? "Menlo-Bold" : "Menlo", size: size) ?? UIFont.monospacedSystemFont(ofSize: size, weight: bold ? .bold : .regular)
        view.addSubview(label)
    }

    private func pill(_ title: String, color: UIColor) -> UIButton {
        let b = UIButton(type: .system)
        b.setTitle(title, for: .normal)
        b.setTitleColor(.white, for: .normal)
        b.backgroundColor = color
        b.titleLabel?.font = UIFont.systemFont(ofSize: 14, weight: .heavy)
        b.layer.cornerRadius = 0
        return b
    }
}
