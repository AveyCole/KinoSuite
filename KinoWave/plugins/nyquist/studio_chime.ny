;nyquist plug-in
;version 4
;type generate
;name "Studio Bell Chime (Nyquist)"
(mult (sum (scale 0.6 (osc 72 2.0)) (scale 0.3 (osc 79 2.0)) (scale 0.15 (osc 84 2.0))) (pwl 0.01 1.0 0.4 0.35 2.0 0.0))
