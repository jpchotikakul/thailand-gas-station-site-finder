/* Client-side reweighting. Factor scores are computed in the pipeline and are
   not invented in the browser. Changing the sliders only changes how those
   existing factor scores are averaged, and updates completeness (share of
   weight that came from computed, not imputed, factors). */
(function (global) {
  const DEFAULT_WEIGHTS = {
    traffic: 30,
    road_access: 20,
    land_size: 15,
    competition: 15,
    demand: 10,
    price_value: 10,
  };

  function band(score) {
    if (score == null || Number.isNaN(score)) return null;
    if (score >= 70) return "high";
    if (score >= 45) return "medium";
    return "low";
  }

  function reweight(listing, weights) {
    const src = weights || DEFAULT_WEIGHTS;
    const total = Object.values(src).reduce((a, b) => a + Number(b || 0), 0) || 1;
    const w = {};
    Object.keys(DEFAULT_WEIGHTS).forEach((k) => {
      w[k] = (Number(src[k] || 0) / total) * 100;
    });
    const factors = (listing.scores && listing.scores.factors) || {};
    let overall = 0;
    let computedWeight = 0;
    Object.keys(DEFAULT_WEIGHTS).forEach((k) => {
      const f = factors[k] || {};
      const s = f.score;
      if (s != null) overall += Number(s) * w[k];
      if (f.status === "computed") computedWeight += w[k];
    });
    overall = Math.round((overall / 100) * 10) / 10;
    return {
      overall,
      band: band(overall),
      completeness: Math.round((computedWeight / 100) * 1000) / 1000,
      weights: w,
    };
  }

  global.SiteScore = { DEFAULT_WEIGHTS, band, reweight };
})(window);
