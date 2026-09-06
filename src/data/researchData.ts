import { ResearchCard } from '../types';

export const INITIAL_RESEARCH_CARDS: ResearchCard[] = [
  {
    id: 'card-1',
    title: 'Neuro-Symbolic Reasoning in Autonomous Deep Exploration Agents',
    domain: 'arxiv.org',
    domainFavicon: 'arXiv',
    category: 'Cognitive Computing',
    matchScore: 99,
    author: 'Dr. Elena Rostova et al.',
    institution: 'Stanford Institute for Human-Centered AI',
    readTime: '6 min read',
    publishedDate: 'March 2026',
    thumbnailUrl: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop&q=80',
    summary: 'Bridging connectionist transformer neural architectures with formal first-order logic proofs, enabling zero-shot planning that guarantees physical invariants and eliminate hallucinations.',
    keyFindings: [
      'Eliminated 94.2% of hallucination errors in multi-hop causal reasoning.',
      'Formal logic verifier runs in sub-12ms bounding runtime overhead.',
      'Achieved human-level synthesis across 12,000 multi-step physics benchmarks.'
    ],
    fullArticle: [
      'Modern foundation models excel at statistical pattern generation but repeatedly fail when confronted with rigorous deductive reasoning tasks requiring multi-step mathematical consistency or invariant guarantees.',
      'In this study, we propose Archimedes, a hybrid neuro-symbolic framework that interlaces stochastic token decoding with an active SAT/SMT symbolic engine. When an agent formulates an intermediate hypothesis, the symbolic constraint solver compiles the proposition into formal predicate calculus.',
      'Across extensive robotic manipulation and chemical synthesis trials, Archimedes achieved a 99.4% task completion rate with zero invariant violations, paving the way for verifiable autonomous scientific exploration.'
    ],
    tags: ['Neuro-Symbolic', 'Reasoning', 'Autonomous Agents', 'SMT Solvers'],
    accentColor: 'indigo',
    badge: 'Primary Breakthrough'
  },
  {
    id: 'card-2',
    title: 'Topological Superconductors and Majorana Zero Modes in 2D Heterostructures',
    domain: 'nature.com/physics',
    domainFavicon: 'Nature',
    category: 'Quantum Hardware',
    matchScore: 97,
    author: 'Prof. Marcus Vance & Dr. Aoi Tanaka',
    institution: 'Max Planck Institute for Solid State Research',
    readTime: '8 min read',
    publishedDate: 'February 2026',
    thumbnailUrl: 'https://images.unsplash.com/photo-1635070041078-e363dbe005cb?w=800&auto=format&fit=crop&q=80',
    summary: 'Direct visual confirmation of braided non-Abelian anyonic statistics in monolayer bismuth telluride heterostructures, unlocking fault-tolerant topological qubits.',
    keyFindings: [
      'Coherence lifetime exceeded 420 microseconds at 1.4 Kelvin.',
      'Scanning tunneling spectroscopy verified zero-bias conductance quantization at 2e²/h.',
      'Braiding sequence demonstrated topological invariance against thermal noise.'
    ],
    fullArticle: [
      'Topological quantum computing relies on non-local storage of quantum information in Majorana zero modes (MZMs). Because information is stored globally rather than in local orbital states, topological qubits are inherently immune to local phase perturbations.',
      'Here we engineer a pristine heterostructure comprising a ferromagnetic insulator coupled to an s-wave superconductor via molecular beam epitaxy. By applying an in-plane magnetic gradient, we observe sharp Majorana conductance peaks cleanly isolated at wire boundaries.',
      'This breakthrough removes the need for millikelvin dilution refrigeration, shifting topological qubit testbeds into practical liquid helium operating thresholds.'
    ],
    tags: ['Majorana Modes', 'Quantum Qubits', 'Heterostructures', 'Superconductivity'],
    accentColor: 'cyan',
    badge: 'Quantum Milestone'
  },
  {
    id: 'card-3',
    title: 'Biomimetic Cellular Matrices for Hyper-Scale Carbon Mineralization',
    domain: 'technologyreview.com',
    domainFavicon: 'MIT TR',
    category: 'Climate & Materials',
    matchScore: 95,
    author: 'Claire D. Dubois, Ph.D.',
    institution: 'MIT Department of Materials Science',
    readTime: '5 min read',
    publishedDate: 'January 2026',
    thumbnailUrl: 'https://images.unsplash.com/photo-1507499739999-097706ad8914?w=800&auto=format&fit=crop&q=80',
    summary: 'Porous carbon-sequestering aerogels synthesized from enzyme-catalyzed marine silicate matrices that convert ambient atmospheric CO2 into structural carbonate blocks within hours.',
    keyFindings: [
      'Sequestered 1.48 tons of CO₂ equivalent per metric ton of cured structural aerogel.',
      'Compressive strength exceeded 62 MPa, outperforming standard Portland cement.',
      'Energy consumption reduced by 78% relative to traditional calcination kilns.'
    ],
    fullArticle: [
      'Global construction relies heavily on Ordinary Portland Cement, an industrial sector responsible for roughly 8% of anthropogenic greenhouse emissions annually.',
      'We designed an enzymatic catalyst mimicking carbonic anhydrase bound within an organosilicon scaffold. Ambient air passed across the matrix precipitates calcium and magnesium carbonates directly from dilute gaseous phases without requiring energy-intensive carbon capture and storage (CCS) compression stages.',
      'Life-cycle assessment confirms the cured material is net-negative throughout manufacturing, providing an immediate pathway for carbon-negative urban infrastructure.'
    ],
    tags: ['Carbon Sequestration', 'Biomimetic', 'Aerogels', 'Sustainable Infrastructure'],
    accentColor: 'emerald',
    badge: 'Eco-Sustained'
  },
  {
    id: 'card-4',
    title: 'Optogenetic Synchrony: Decoding High-Frequency Prefrontal Oscillations',
    domain: 'cell.com/neuroscience',
    domainFavicon: 'Cell',
    category: 'Neurobiology',
    matchScore: 94,
    author: 'Dr. Tariq Al-Mansoor & Team',
    institution: 'Oxford Center for Human Brain Activity',
    readTime: '7 min read',
    publishedDate: 'February 2026',
    thumbnailUrl: 'https://images.unsplash.com/photo-1559757175-5700dde675bc?w=800&auto=format&fit=crop&q=80',
    summary: 'High-density micro-LED optogenetic stimulation of cortical interneurons reveals the 140Hz gamma sub-band coordinating working memory retrieval and cross-modal sensory fusion.',
    keyFindings: [
      'Sub-millisecond optical control of parvalbumin-positive basket cells.',
      'Direct coupling discovered between ventral striatum gating and dorsolateral prefrontal cortex.',
      'Demonstrated 38% recovery of cognitive recall in neurodegenerative mouse models.'
    ],
    fullArticle: [
      'Gamma oscillations (30–80 Hz) have long been implicated in conscious sensory binding, but recent wide-field optical recordings have identified distinct ultra-fast ripple bursts exceeding 120 Hz during decisive cognitive transitions.',
      'Using a two-photon holographic optogenetics setup, we mapped individual interneuron arrays in behaving primates performing dual-task switching paradigms. We found that stimulating specific micro-columns at precisely timed intervals instantaneously refreshed decaying mental representations.',
      'These findings lay the groundwork for closed-loop non-invasive neural prostheses tailored to mitigate cognitive decline in neurodegenerative diseases.'
    ],
    tags: ['Optogenetics', 'Prefrontal Cortex', 'Gamma Waves', 'Neural Prosthetics'],
    accentColor: 'violet',
    badge: 'Neuro Discovery'
  },
  {
    id: 'card-5',
    title: 'Zero-Knowledge Cryptographic Rollups with Constant-Time Verification',
    domain: 'ieee.org/security',
    domainFavicon: 'IEEE',
    category: 'Cryptography',
    matchScore: 93,
    author: 'Kavita Sundaram & Julian Mercer',
    institution: 'ETH Zürich Cryptography Lab',
    readTime: '9 min read',
    publishedDate: 'March 2026',
    thumbnailUrl: 'https://images.unsplash.com/photo-1639762681485-074b7f938ba0?w=800&auto=format&fit=crop&q=80',
    summary: 'A new recursive polynomial commitment scheme enabling cryptographic proofs for 500,000 off-chain transactions verified on-chain in exactly 3.2 milliseconds.',
    keyFindings: [
      'Proof size compressed to a constant 184 bytes independent of circuit complexity.',
      'Linear prover runtime without trusted setup ceremony requirements.',
      'Post-quantum resistant against Shor algorithm lattice reduction attacks.'
    ],
    fullArticle: [
      'Scalability remains the holy grail of distributed ledger networks. While optimistic rollups suffer from seven-day dispute periods, classic zk-SNARK constructions require cumbersome trusted setup ceremonies or grow logarithmically with recursive proof batching.',
      'We introduce Helix-STARK, a lattice-based commitment protocol leveraging ring learning-with-errors (Ring-LWE). Helix generates recursive folding proofs where verifier work remains strictly O(1), consuming only 28,000 gas units on the Ethereum Virtual Machine.',
      'Benchmarking against industry standards showcases a 40x speedup in decentralized settlement throughput while preserving strict mathematical zero-knowledge guarantees.'
    ],
    tags: ['Zero-Knowledge', 'Cryptography', 'Lattice Schemes', 'Rollups'],
    accentColor: 'amber',
    badge: 'Cryptographic'
  },
  {
    id: 'card-6',
    title: 'Perovskite-Silicon Tandem Photovoltaics Exceeding 34% Certified Efficiency',
    domain: 'science.org/energy',
    domainFavicon: 'Science',
    category: 'Clean Tech',
    matchScore: 92,
    author: 'Dr. Henrik Lindqvist',
    institution: 'Fraunhofer Institute for Solar Energy Systems',
    readTime: '5 min read',
    publishedDate: 'January 2026',
    thumbnailUrl: 'https://images.unsplash.com/photo-1509391365360-2e959784a276?w=800&auto=format&fit=crop&q=80',
    summary: 'Self-assembling dipole monolayers passivate interfacial traps in wide-bandgap metal halide perovskites, pushing dual-junction operational efficiency to commercial thresholds.',
    keyFindings: [
      'Achieved 34.6% certified steady-state power conversion efficiency.',
      'Maintained 96% output after 2,000 hours of continuous thermal damp-heat aging.',
      'Roll-to-roll printing compatibility confirmed at under $0.18 per watt.'
    ],
    fullArticle: [
      'Silicon solar cells are rapidly approaching their theoretical Shockley-Queisser single-junction ceiling of 29.4%. Tandem architectures combining wide-bandgap perovskites on top of textured silicon bottom cells offer the clearest route to higher photon capture.',
      'Previous iterations degraded rapidly under ambient moisture and ultraviolet light. Our chemical approach replaces volatile organic cations with fluorinated inorganic anchor molecules, yielding hydrophobic interfaces that block ion migration.',
      'Outdoor field deployments across variable desert and temperate microclimates showed zero delamination, heralding the mass transition of solar gigafactories to tandem lines.'
    ],
    tags: ['Perovskite', 'Solar Energy', 'Photovoltaics', 'Clean Tech'],
    accentColor: 'yellow',
    badge: 'Clean Energy'
  },
  {
    id: 'card-7',
    title: 'Kinematic Fluid Dynamics in Active Micro-Robotic Swarms',
    domain: 'prl.aps.org',
    domainFavicon: 'APS',
    category: 'Micro-Robotics',
    matchScore: 91,
    author: 'Dr. Sheng Wu & Prof. Beatrice Thorne',
    institution: 'Caltech Department of Aerospace & Bioengineering',
    readTime: '6 min read',
    publishedDate: 'February 2026',
    thumbnailUrl: 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=800&auto=format&fit=crop&q=80',
    summary: 'Magnetic helical micro-swimmers exploit non-Newtonian viscoelastic shear thinning in human capillary beds to deliver targeted therapeutics without vascular occlusion.',
    keyFindings: [
      'Navigated low Reynolds number flow regimes (Re ~ 10⁻⁴) with 98% precision.',
      'Autonomous acoustic beacon triangulation provided real-time 3D tracking.',
      'Delivered localized anti-thrombotic payloads in vivo without systemic side effects.'
    ],
    fullArticle: [
      'Navigating fluid environments at the micro-scale presents profound physical challenges: at low Reynolds numbers, viscous forces completely dominate inertial forces, rendering reciprocal reciprocal strokes useless (Purcell\'s Scallop Theorem).',
      'We designed corkscrew flagella propelled by rotating magnetic vector fields. By tuning the pitch of the artificial flagella to resonance frequencies of blood plasma polymer chains, each micro-robot generates localized vortex flows that pull neighboring swarm agents into cohesive aerodynamic formations.',
      'Targeted in-vivo murine studies proved complete resolution of targeted blood clots in under 8 minutes, dramatically minimizing surgical invasiveness.'
    ],
    tags: ['Micro-Swimmers', 'Fluid Mechanics', 'Targeted Delivery', 'Swarms'],
    accentColor: 'sky',
    badge: 'Robotics'
  },
  {
    id: 'card-8',
    title: 'Non-Euclidean Latent Geometric Embeddings for Structural Proteomics',
    domain: 'biorxiv.org',
    domainFavicon: 'BioRxiv',
    category: 'Computational Biology',
    matchScore: 90,
    author: 'Miriam O’Connor, Ph.D.',
    institution: 'Wellcome Sanger Institute',
    readTime: '7 min read',
    publishedDate: 'March 2026',
    thumbnailUrl: 'https://images.unsplash.com/photo-1532094349884-543bc11b234d?w=800&auto=format&fit=crop&q=80',
    summary: 'Hyperbolic Riemannian manifolds encode macromolecular conformational ensembles, predicting cryptic allosteric drug binding pockets missed by static crystal structures.',
    keyFindings: [
      'Predicted allosteric sites with 91.8% structural agreement on cryo-EM benchmarks.',
      'Reduced dimensional representation size by 85% compared to Euclidean vectors.',
      'Identified previously undocumented transient binding crevices in KRAS G12D.'
    ],
    fullArticle: [
      'Biological macromolecules are inherently dynamic: proteins oscillate between multiple conformational landscapes to execute signaling and enzymatic catalysis. Standard graph neural networks mapping structures into flat Euclidean coordinates distort long-range hierarchical couplings.',
      'By projecting atomic contact topologies into negative-curvature hyperbolic Poincaré balls, our model naturally accommodates hierarchical branching without artificial distortion. The learned geometric geodesics correlate directly with structural transition pathways.',
      'We demonstrate practical application by identifying a novel allosteric binding pocket on an oncogenic mutant protein, validating the computational predictions through NMR spectroscopy.'
    ],
    tags: ['Hyperbolic Geometry', 'Proteomics', 'Structural Biology', 'Allosteric Drugs'],
    accentColor: 'rose',
    badge: 'Bio-Informatics'
  },
  {
    id: 'card-9',
    title: 'Sub-Kelvin Thermal Boundary Transport in 3D Integrated Photonics',
    domain: 'optica.org/letters',
    domainFavicon: 'Optica',
    category: 'Photonics',
    matchScore: 88,
    author: 'Leonard Zhang & Dr. Sofia Rossi',
    institution: 'Harvard John A. Paulson SEAS',
    readTime: '6 min read',
    publishedDate: 'January 2026',
    thumbnailUrl: 'https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=800&auto=format&fit=crop&q=80',
    summary: 'Phonon-engineered silicon nitride boundary interlayers dissipate cryo-optical heat loads in superconducting nanowire single-photon detector arrays.',
    keyFindings: [
      'Kapitza thermal conductance improved by 4.2x across the dielectric interface.',
      'Reduced detector dark count rates to below 0.05 Hz per channel.',
      'Facilitated 1,024-pixel monolithic superconducting optical readout arrays.'
    ],
    fullArticle: [
      'Superconducting Nanowire Single-Photon Detectors (SNSPDs) represent the gold standard for quantum optical communication, deep-space optical links, and lidar. However, thermal coupling between the superconducting film and the silicon substrate limits multi-pixel scaling.',
      'By etching nanoscale acoustic metamaterial gratings into the silicon nitride interface, we matched phonon acoustic impedances, preventing phonon back-scattering and hot-spot quenching.',
      'This architecture allows dense 2D detector arrays to operate under heavy laser strobe conditions without thermal runaway or crosstalk.'
    ],
    tags: ['Photonics', 'SNSPD', 'Superconducting', 'Thermal Transport'],
    accentColor: 'purple',
    badge: 'Optics'
  },
  {
    id: 'card-10',
    title: 'Human-Centric Explainability in Real-Time Agentic Workflows',
    domain: 'dl.acm.org/chi',
    domainFavicon: 'ACM CHI',
    category: 'HCI & AI Governance',
    matchScore: 87,
    author: 'Prof. David K. Vance & Maya Lin',
    institution: 'Carnegie Mellon University HCI Institute',
    readTime: '5 min read',
    publishedDate: 'February 2026',
    thumbnailUrl: 'https://images.unsplash.com/photo-1457369804613-52c61a468e7d?w=800&auto=format&fit=crop&q=80',
    summary: 'A calibrated cognitive trust framework utilizing spatial progressive disclosure and interactive provenance inspection for autonomous collaborative decision-making.',
    keyFindings: [
      'Reduced user decision fatigue by 44% compared to linear raw log feeds.',
      'Increased operator intervention accuracy from 61% to 89% during edge-case failures.',
      'Established open evaluation metrics for auditability in mission-critical autonomy.'
    ],
    fullArticle: [
      'As AI agents transition from advisory assistants to autonomous decision-makers in aviation, medicine, and critical infrastructure, the traditional "black box" explainability problem transforms into a real-time cognitive bandwidth bottleneck.',
      'We conducted a longitudinal study with 240 domain specialists across healthcare and logistics. Interfaces that offer tiered contextual transparency—showing immediate action hypotheses with interactive backtrackable provenance stacks—dramatically outperformed passive dashboards.',
      'Our guidelines demonstrate that spatial affordances, card-stacking interaction models, and tactile tactile queues foster accurate human calibration of autonomous agent decisions.'
    ],
    tags: ['Human-AI Interaction', 'Explainability', 'Cognitive Ergonomics', 'Trust'],
    accentColor: 'teal',
    badge: 'HCI Research'
  }
];
