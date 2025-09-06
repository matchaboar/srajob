import { useQuery, useMutation } from "convex/react";
import { api } from "../convex/_generated/api";
import { SignInForm } from "./SignInForm";
import { useEffect } from "react";

export function PublicJobPreview() {
  const recentJobs = useQuery(api.jobs.getRecentJobs);
  const jobsExist = useQuery(api.jobs.checkIfJobsExist);
  const insertFakeJobs = useMutation(api.seedData.insertFakeJobs);

  // Auto-insert fake jobs if none exist
  useEffect(() => {
    if (jobsExist === false) {
      insertFakeJobs({}).catch(console.error);
    }
  }, [jobsExist, insertFakeJobs]);

  const formatSalary = (amount: number) => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  // Show only first 5 jobs for preview
  const previewJobs = recentJobs?.slice(0, 5) || [];

  return (
    <div className="max-w-6xl mx-auto p-6">
      {/* Hero Section */}
      <div className="text-center mb-8">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">
          Find Your Next Opportunity
        </h1>
        <p className="text-xl text-gray-600 max-w-2xl mx-auto">
          Discover thousands of job opportunities from top companies. 
          Apply with AI assistance or manually - your choice.
        </p>
      </div>

      {/* Login Banner */}
      <div className="bg-gradient-to-r from-blue-600 to-purple-600 text-white p-6 rounded-lg shadow-lg mb-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold mb-2">
            Only 5 jobs are displayed for free. Log in to see more.
          </h2>
          <p className="text-blue-100 mb-4">
            Access thousands of job listings, advanced search filters, and AI-powered applications.
          </p>
        </div>
      </div>

      {/* Job Preview Section */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold text-gray-900 mb-6">Latest Job Opportunities</h2>
        
        {previewJobs.length > 0 ? (
          <div className="space-y-0">
            {previewJobs.map((job, index) => (
              <div 
                key={job._id} 
                className={`bg-white p-3 shadow-sm border-b border-gray-200 first:rounded-t-lg last:rounded-b-lg last:border-b-0 transition-all hover:shadow-md ${
                  index >= 3 ? 'opacity-75' : ''
                }`}
              >
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-lg font-semibold text-gray-900">{job.title}</h3>
                      <span className="px-2 py-0.5 bg-blue-100 text-blue-800 text-xs font-medium rounded-full">
                        {job.level}
                      </span>
                      {job.remote && (
                        <span className="px-2 py-0.5 bg-green-100 text-green-800 text-xs font-medium rounded-full">
                          Remote
                        </span>
                      )}
                    </div>
                    <p className="text-base font-medium text-gray-700 mb-0.5">{job.company}</p>
                    <p className="text-sm text-gray-600 mb-1">{job.location}</p>
                    <p className="text-sm text-gray-700 mb-2 line-clamp-2">{job.description}</p>
                    <div className="flex items-center gap-4 text-xs text-gray-600">
                      <span className="font-medium text-green-600">
                        {formatSalary(job.totalCompensation)}
                      </span>
                      <span>Posted {new Date(job.postedAt).toLocaleDateString()}</span>
                    </div>
                  </div>

                  <div className="flex flex-col gap-1 ml-4">
                    <button
                      disabled
                      className="px-3 py-1.5 bg-gray-200 text-gray-500 rounded-md text-xs font-medium cursor-not-allowed"
                    >
                      Sign in to Apply
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="bg-white p-12 rounded-lg shadow-sm text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
            <p className="text-gray-500">Loading job opportunities...</p>
          </div>
        )}
      </div>

      {/* Call to Action */}
      <div className="bg-gray-100 p-8 rounded-lg text-center">
        <h3 className="text-2xl font-bold text-gray-900 mb-4">
          Ready to Find Your Dream Job?
        </h3>
        <p className="text-gray-600 mb-6 max-w-2xl mx-auto">
          Join thousands of job seekers who have found their perfect role. 
          Get access to advanced search filters, personalized recommendations, 
          and AI-powered application assistance.
        </p>
        <div className="max-w-md mx-auto">
          <SignInForm />
        </div>
      </div>
    </div>
  );
}
