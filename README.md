# SafeRoute-AI

SafeRoute-AI is a dynamic, risk-aware navigation system that prioritizes personal safety alongside travel efficiency. Unlike standard navigation tools that only calculate the fastest or shortest path, SafeRoute-AI analyzes multiple safety and environmental risk factors to find the most secure route for any time of day.

---

## 🔍 Why? (The Motivation)

Standard mapping applications (like Google Maps or Apple Maps) are designed around a single primary objective: **minimizing travel time or distance**. 

However, speed is not always the most critical factor when traveling. For many people—especially individuals traveling alone late at night, women, elderly citizens, or emergency responders—**safety is the primary concern**. 
- A route that saves 2 minutes but requires walking through a dark, isolated alley or an area with high crime rates is not a viable option.
- SafeRoute-AI was created to **put safety first**, giving users agency over their routes by letting them choose how they want to balance travel time against potential risks.

---

## 🛠️ What Problems It Solves?

SafeRoute-AI addresses several critical real-world navigation challenges:

1. **Darkness and Poor Lighting**: Automatically routes users away from streets with poor or missing streetlights, especially during nighttime.
2. **Urban Isolation**: Identifies and avoids deserted or low-traffic streets where help is far away.
3. **High-Crime Areas**: Steers routes away from zones with high historic or active crime rates.
4. **Dynamic Time-of-Day Risk**: A road that is perfectly safe at 12:00 PM (noon) may become risky at 12:00 AM (midnight). The routing engine dynamically recalculates risk factors hour-by-hour.
5. **Environmental Hazards**: Integrates waterlogging and flood risk data to steer clear of impassable routes during heavy rain.
6. **Emergency Distress (SOS)**: In dangerous situations, users can instantly calculate the fastest and safest route to the nearest **Safe Haven** (e.g., police stations, hospitals, or emergency shelters).
7. **One-Size-Fits-All Routing**: SafeRoute-AI replaces rigid routing with customizable safety profiles matching the user's specific context.

---

## 🚀 How? (Under the Hood)

SafeRoute-AI operates as a full-stack web application powered by a custom mathematical routing engine.

### 1. The Core Routing Engine (`Engine/`)
The backend is written in Python (using `numpy`, `pandas`, and `scipy`) for extreme performance and millisecond-level routing latency:
* **The Graph**: At startup, it loads the road network of Central Bangalore (2,929 nodes and 5,675 edges) into memory.
* **The Snapping (KD-Tree)**: It builds a fast spatial KD-Tree that snaps any GPS coordinate (latitude/longitude) to the nearest intersection in the graph in $O(\log N)$ time.
* **Vectorized Cost Model**: Every road segment (edge) has a base travel time that is inflated by a composite risk score based on the selected mode:
  $$\text{Cost} = \text{Travel Time} \times \left(1 + \text{Risk Scale} \times \text{Composite Risk}\right)$$
* **A\* Search Algorithm**: Uses an optimized A\* pathfinding algorithm with a Haversine distance heuristic to compute the optimal route on the fly.

### 2. Safety Profiles
Users can choose between 5 distinct routing profiles, each adjusting how risk factors are weighted:

| Profile | Crime Weight | Lighting Weight | Isolation Weight | CCTV Weight | Police Proximity | Best For |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| 🚀 **Fastest** | Minimal | None | None | None | None | Normal daytime commutes where speed is priority |
| 🛡️ **Safest** | Maximum | Maximum | High | Medium | Medium | General nighttime safety |
| ⚖️ **Balanced** | Medium | Medium | Medium | Low | Low | A standard blend of safety and travel time |
| 👩 **Women Safety** | Maximum | Maximum | Maximum | High | High | Enhanced security with CCTV and police proximity |
| 🚨 **Emergency** | Low | Low | Low | None | None | Fastest viable routes to escape immediate danger |

### 3. SOS Safe Haven Routing
When the SOS button is triggered, the engine:
1. Instantly queries the KD-Tree for the 3 nearest safe havens (police stations/hospitals).
2. Calculates the optimal routes to all of them using the **Emergency** safety profile.
3. Selects the one with the shortest travel time and returns the route immediately.

### 4. Technical Architecture
```
   [ Browser (Next.js UI on Vercel) ]
                 │
                 ▼ (HTTPS / REST API)
   [ Backend Container (FastAPI on Cloud Run) ]
        │                       │
        ▼ (Loads Graph)         ▼ (Loads Live Overlay)
   [ MongoDB Atlas ]     [ Local CSVs (Datasets/) ]
```
* **Frontend**: Built with Next.js, TypeScript, and a map interface showing the active route, hourly safety ribbons, and risk overlays.
* **Backend**: Powered by FastAPI, containerized using Docker, and deployed on Google Cloud Run. It pulls raw points from MongoDB at startup to construct the in-memory routing graph.

---

## 📖 Related Documentation

* For deployment steps (GCP Cloud Run + Vercel + MongoDB), check out [DEPLOY.md](./DEPLOY.md).
* For detailed instructions on running the Frontend and Backend locally, see [Frontend/saferoute-ai/README.md](./Frontend/saferoute-ai/README.md).
