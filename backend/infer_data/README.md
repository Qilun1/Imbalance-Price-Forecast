# infer_data

Inferred 10 h forecast sets (gitignored). One row per model version, forecast origin and step, with
every submission column (`p10`, `p50`, `p90`, `p_up`, `p_down`, `p_none`, `p_spike_high`,
`p_spike_low`, `data_cutoff_utc`, `top_drivers`). The dashboard reads from here; the submission CSV
is exported from here.
