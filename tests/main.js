const submitFilesToBackend = async () => {
  // Only transmit files containing a 'valid' status filter
  const targetsToUpload = files.filter((f) => f.status === "valid");
  if (targetsToUpload.length === 0) return;

  const formData = new FormData();

  targetsToUpload.forEach((item) => {
    formData.append("file_binaries", item.file);
  });

  try {
    const response = await fetch("http://localhost:3000/upload-modules", {
      method: "POST",
      body: formData,
    });

    if (response.ok) {
      console.log("Files successfully ingested by FastAPI");
      console.log(response.message)
    }
  } catch (error) {
    console.error("Transmission breakdown:", error);
  }
};
