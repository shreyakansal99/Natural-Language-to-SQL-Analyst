export default function UserBar({ auth, onLogout }) {
  return (
    <div className="userbar">
      Signed in as <strong>{auth.username}</strong> ({auth.role})
      <button className="secondary" onClick={onLogout}>Log out</button>
    </div>
  );
}