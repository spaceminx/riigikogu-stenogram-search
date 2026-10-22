import React from "react";

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary püüdis vea:", error, errorInfo);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="glass-panel"
          role="alert"
          style={{
            padding: "3rem 1.5rem",
            textAlign: "center",
            margin: "2rem auto",
            maxWidth: "600px",
          }}
        >
          <h2 style={{ fontSize: "1.75rem", marginBottom: "0.5rem" }}>Midagi läks valesti</h2>
          <p
            style={{
              color: "var(--text-secondary, #64748b)",
              marginBottom: "2rem",
              lineHeight: 1.6,
            }}
          >
            Lehe kuvamisel tekkis ootamatu viga.
          </p>
          <button
            type="button"
            className="search-button"
            onClick={this.handleReload}
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: "pointer",
            }}
          >
            Laadi leht uuesti
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
