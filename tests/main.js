const response = await fetch("http://localhost:3000/greet", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    name: "Ruben",
  }),
});

const data = await response.json();

console.log(data.message);