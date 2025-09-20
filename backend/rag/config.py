DEFAULTS = {
  'alpha_embed': 0.55,              # weight for embedding score vs BM25
  'boost_table_when_numbers': 1.25, # multiplicative boost
  'boost_binding_normativity': 1.15,
  'boost_standard_match': 1.20,
  'boost_heading_level_decay': 0.03, # per level (higher level => smaller boost)
  'boost_recent_section_neighbor': 1.08,
  'k_neighborhood': 1,              # pull prev/next chunk in section
  'max_xref_hops': 1,
  'top_k_initial': 50,
  'top_k_final': 12
}
