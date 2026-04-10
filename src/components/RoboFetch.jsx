/**
 * RoboFetch — A small robot runs across a track pulling the next question card.
 *
 * Entirely pure CSS animation — no libraries.
 * The robot has a body, two running legs, antenna, and eye.
 * It pulls a rope attached to a question card that slides in from the right.
 * Dust puffs trail behind the robot's feet.
 */
export default function RoboFetch({ questionNumber, total }) {
  return (
    <div className="robo-stage" aria-live="polite" aria-label="Loading next question">
      {/* Ground / track */}
      <div className="robo-track">
        <div className="robo-track-line" />
        <div className="robo-track-dashes" />
      </div>

      {/* The running robot */}
      <div className="robo-runner">
        {/* Dust puffs behind the robot */}
        <div className="robo-dust">
          <span className="dust-puff dust-1" />
          <span className="dust-puff dust-2" />
          <span className="dust-puff dust-3" />
        </div>

        {/* Robot body */}
        <div className="robo-body">
          {/* Antenna */}
          <div className="robo-antenna">
            <div className="robo-antenna-stem" />
            <div className="robo-antenna-ball" />
          </div>

          {/* Head */}
          <div className="robo-head">
            <div className="robo-eye" />
            <div className="robo-mouth" />
          </div>

          {/* Torso */}
          <div className="robo-torso">
            <div className="robo-chest-light" />
          </div>

          {/* Arms */}
          <div className="robo-arm robo-arm-back" />
          <div className="robo-arm robo-arm-front" />

          {/* Legs */}
          <div className="robo-leg robo-leg-back" />
          <div className="robo-leg robo-leg-front" />
        </div>

        {/* Rope from robot to card */}
        <div className="robo-rope" />

        {/* Question card being pulled */}
        <div className="robo-card">
          <div className="robo-card-icon">?</div>
          <div className="robo-card-lines">
            <span /><span /><span />
          </div>
        </div>
      </div>

      {/* Label */}
      <p className="robo-label">
        Fetching question {questionNumber}{total ? ` of ${total}` : ''}...
      </p>
    </div>
  );
}
