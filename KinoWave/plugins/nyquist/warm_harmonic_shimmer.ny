;nyquist plug-in
;version 4
;type process
;name "Warm Harmonic Shimmer (Nyquist)"
;info "Adds gentle harmonic presence and low-pass warmth"
(sum (scale 0.85 s) (scale 0.15 (lp s 2800)))
